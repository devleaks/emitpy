# Airport as defined in X-Plane
#
import os.path
import re
import logging

from geojson import Point, Polygon, Feature
from turfpy.measurement import distance, destination, bearing

from .airport import AirportBase
from ..airspace import CIFP
from ..graph import Vertex, Edge
from ..geo import Ramp, ServiceParking, Runway, mkPolygon
from ..parameters import DATA_DIR

SYSTEM_DIRECTORY = os.path.join(DATA_DIR, "x-plane")

logger = logging.getLogger("XPAirport")


# ################################@
# APT LINE
#
#
class AptLine:
    # APT.DAT line for this airport
    def __init__(self, line):
        self.arr = line.split()
        if len(self.arr) == 0:
            logger.debug(":linecode: empty line? '%s'", line)

    def linecode(self):
        if len(self.arr) > 0:
            return int(self.arr[0])
        return None

    def content(self):
        if len(self.arr) > 1:
            return " ".join(self.arr[1:])
        return None  # line has no content

    def __str__(self):
        return " ".join(self.arr)


# ################################@
# XP AIRPORT
#
#
class XPAirport(AirportBase):
    """
    Airport represetation
    """
    def __init__(self, icao: str, iata: str, name: str, city: str, country: str, region: str, lat: float, lon: float, alt: float):
        AirportBase.__init__(self, icao=icao, iata=iata, name=name, city=city, country=country, region=region, lat=lat, lon=lon, alt=alt)
        self.scenery_pack = False
        self.lines = []
        self.atc_ground = None
        self.loaded = False
        self.procedures
        self.simairporttype = "X-Plane"

    def loadFromFile(self):
        SCENERY_PACKS = os.path.join(SYSTEM_DIRECTORY, "Custom Scenery", "scenery_packs.ini")
        scenery_packs = open(SCENERY_PACKS, "r")
        scenery = scenery_packs.readline()
        scenery = scenery.strip()

        while not self.loaded and scenery:  # while we have not found our airport and there are more scenery packs
            if re.match("^SCENERY_PACK", scenery, flags=0):
                logger.debug("SCENERY_PACK %s", scenery.rstrip())
                scenery_pack_dir = scenery[13:-1]
                scenery_pack_apt = os.path.join(SYSTEM_DIRECTORY, scenery_pack_dir, "Earth nav data", "apt.dat")
                logger.debug("APT.DAT %s", scenery_pack_apt)

                if os.path.isfile(scenery_pack_apt):
                    apt_dat = open(scenery_pack_apt, "r", encoding='utf-8')
                    line = apt_dat.readline()

                    while not self.loaded and line:  # while we have not found our airport and there are more lines in this pack
                        if re.match("^1 ", line, flags=0):  # if it is a "startOfAirport" line
                            newparam = line.split()  # if no characters supplied to split(), multiple space characters as one
                            # logger.debug("airport: %s" % newparam[4])
                            if newparam[4] == self.icao:  # it is the airport we are looking for
                                self.name = " ".join(newparam[5:])
                                self.altitude = newparam[1]
                                # Info 4.a
                                logger.info(":loadFromFile: Found airport %s '%s' in '%s'.", newparam[4], self.name, scenery_pack_apt)
                                self.scenery_pack = scenery_pack_apt  # remember where we found it
                                self.lines.append(AptLine(line))  # keep first line
                                line = apt_dat.readline()  # next line in apt.dat
                                while line and not re.match("^1 ", line, flags=0):  # while we do not encounter a line defining a new airport...
                                    testline = AptLine(line)
                                    if testline.linecode() is not None:
                                        self.lines.append(testline)
                                    else:
                                        logger.debug(":loadFromFile: did not load empty line '%s'" % line)
                                    line = apt_dat.readline()  # next line in apt.dat
                                # Info 4.b
                                logger.info(":loadFromFile: Read %d lines for %s." % (len(self.lines), self.name))
                                self.loaded = True

                        if(line):  # otherwize we reached the end of file
                            line = apt_dat.readline()  # next line in apt.dat

                    apt_dat.close()

            scenery = scenery_packs.readline()

        scenery_packs.close()
        return [True, "XPAirport::loadFromFile: loaded"]


    def loadProcedures(self):
        self.procedures = CIFP(self.icao)
        return [True, "XPAirport::loadProcedures: loaded"]


    def loadRunways(self):
        #     0     1 2 3    4 5 6 7    8            9               10 11  1213141516   17           18              19 20  21222324
        # 100 60.00 1 1 0.25 1 3 0 16L  25.29609337  051.60889908    0  300 2 2 1 0 34R  25.25546269  051.62677745    0  306 3 2 1 0
        runways = {}
        for aptline in self.lines:
            if aptline.linecode() == 100:  # runway
                args = aptline.content().split()
                runway = mkPolygon(float(args[8]), float(args[9]), float(args[17]), float(args[18]), float(args[0]))
                runways[args[7]] = Runway(args[7], float(args[0]), float(args[8]), float(args[9]), float(args[17]), float(args[18]), runway)
                runways[args[16]] = Runway(args[16], float(args[0]), float(args[17]), float(args[18]), float(args[8]), float(args[9]), runway)

        self.runways = runways
        logger.debug(":loadRunways: added %d runways", len(runways.keys()))
        return [True, "XPAirport::loadRunways loaded"]

    def loadParkings(self):
        # 1300  25.26123160  051.61147754 155.90 gate heavy|jets|turboprops A1
        # 1301 E airline
        # 1202 ignored.
        ramps = {}

        ramp = None
        for aptline in self.lines:
            if aptline.linecode() == 1300: # ramp  name: str, ramptype: str, position: [float], orientation: float, size: str
                args = aptline.content().split()
                name = " ".join(args[5:])
                ramp = Ramp(name=name, ramptype=args[3], position=(float(args[1]),float(args[0])), orientation=float(args[2]), use=args[4])
                ramps[name] = ramp
            elif ramp is not None and aptline.linecode() == 1301: # ramp details
                args = aptline.content().split()
                if len(args) > 0:
                    ramp.addProp("icao-width", args[0])
                if len(args) > 1:
                    ramp.addProp("operation-type", args[1])
                if len(args) > 2:
                    ramp.addProp("airline", args[2])
            else:
                ramp = None

        self.parkings = ramps
        logger.debug(":loadParkings: added %d ramps: %s" % (len(ramps.keys()), ramps.keys()))
        return [True, "XPAirport::loadParkings loaded"]

    def loadTaxiways(self):
        # Collect 1201 and (102,1204) line codes and create routing network (graph) of taxiways
        # 1201  25.29549372  051.60759816 both 16 unnamed entity(split)
        def addVertex(aptline):
            args = aptline.content().split()
            return self.taxiways.add_vertex(Vertex(node=args[3], point=Point((float(args[0]), float(args[1]))), usage=[ args[2]], name=" ".join(args[3:])))

        vertexlines = list(filter(lambda x: x.linecode() == 1201, self.lines))
        v = list(map(addVertex, vertexlines))
        logger.debug(":loadTaxiways: added %d vertices" % len(v))

        # 1202 20 21 twoway runway 16L/34R
        # 1204 departure 16L,34R
        # 1204 arrival 16L,34R
        # 1204 ils 16L,34R
        edgeCount = 0   # just for info
        edgeActiveCount = 0
        edge = False
        for aptline in self.lines:
            if aptline.linecode() == 1202: # edge
                args = aptline.content().split()
                if len(args) >= 4:
                    src = self.taxiways.get_vertex(args[0])
                    dst = self.taxiways.get_vertex(args[1])
                    cost = distance(src.geometry, dst.geometry)
                    edge = None
                    if len(args) == 5:
                        # args[2] = {oneway|twoway}, args[3] = {runway|taxiway}
                        edge = Edge(src=src, dst=dst, weight=cost, directed=(args[2]=="oneway"), usage=[args[3]], name=args[4])
                    else:
                        edge = Edge(src, dst, cost, args[2], args[3], "")
                    self.taxiways.add_edge(edge)
                    edgeCount += 1
                else:
                    logger.debug(":loadTaxiways: not enough params %d %s.", aptline.linecode(), aptline.content())
            elif aptline.linecode() == 1204 and edge:
                args = aptline.content().split()
                if len(args) >= 2:
                    edge.use(args[0], True)
                    edge.use(args[1], True)
                    edgeActiveCount += 1
                else:
                    logger.debug(":loadTaxiways: not enough params %d %s.", aptline.linecode(), aptline.content())
            else:
                edge = False

        # Info 6
        logger.info(":loadTaxiways: added %d nodes, %d edges (%d enhanced).", len(vertexlines), edgeCount, edgeActiveCount)
        return [True, "XPAirport::loadTaxiways loaded"]

    def loadServiceRoads(self):
        # Collect 1201 and 1206 line codes and create routing network (graph) of service roads
        # 1201  25.29549372  051.60759816 both 16 unnamed entity(split)
        def addVertex(aptline):
            args = aptline.content().split()
            return self.service_roads.add_vertex(Vertex(node=args[3], point=Point((float(args[0]), float(args[1]))), usage=[ args[2]], name=" ".join(args[3:])))

        vertexlines = list(filter(lambda x: x.linecode() == 1201, self.lines))
        v = list(map(addVertex, vertexlines))
        logger.debug(":loadServiceNetwork: added %d vertices" % len(v))

        # 1206 107 11 twoway C
        edgeCount = 0   # just for info
        edge = False
        for aptline in self.lines:
            if aptline.linecode() == 1206: # edge for ground vehicle
                args = aptline.content().split()
                if len(args) >= 4:
                    src = self.service_roads.get_vertex(args[0])
                    dst = self.service_roads.get_vertex(args[1])
                    cost = distance(src.geometry, dst.geometry)
                    edge = None
                    if len(args) == 5:
                        # args[2] = {oneway|twoway}
                        edge = Edge(src=src, dst=dst, weight=cost, directed=(args[2]=="oneway"), usage=["ground"], name=args[4])
                    else:
                        edge = Edge(src, dst, cost, args[2], args[3], "")
                    self.service_roads.add_edge(edge)
                    edgeCount += 1
                else:
                    logger.debug(":loadServiceNetwork: not enough params %d %s.", aptline.linecode(), aptline.content())
            else:
                edge = False

        # Info 6
        logger.info(":loadServiceNetwork: added %d nodes, %d edges.", len(vertexlines), edgeCount)
        return [True, "XPAirport::loadServiceNetwork loaded"]

    def loadServiceDestinations(self):
        # 1400 47.44374472 -122.30463464 88.1 baggage_train 3 Svc Baggage
        # 1401 47.44103438 -122.30382493 0.0 baggage_train Luggage Train Destination South 2
        service_destinations = {}

        for aptline in self.lines:
            if aptline.linecode() in [1400, 1401]:  # service vehicle paarking or destination
                args = aptline.content().split()
                name = " ".join(args[4:])
                service_destinations[name] = ServiceParking(name=name, parking_type=aptline.linecode(), position=(float(args[1]),float(args[0])), orientation=float(args[2]), use=args[3])

        self.service_destinations = service_destinations
        logger.debug(":loadServiceDestination: added %d service_destinations", len(service_destinations.keys()))
        return [True, "XPAirport::loadServiceDestination loaded"]
