# Airport as defined in X-Plane
#
import os.path
import re
import logging
import random

from geojson import Point, Polygon, Feature
from turfpy.measurement import distance, destination, bearing

from .airport import AirportBase
from ..graph import Vertex, Edge, USAGE_TAG
from ..geo import Ramp, ServiceParking, Runway, mkPolygon, findFeatures, FeatureWithProps
from ..parameters import DATA_DIR
from ..constants import TAKEOFF_QUEUE_SIZE, FEATPROP, POI_TYPE, TAG_SEP

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
        self.procedures = None
        self.aeroway_pois = None
        self.service_pois = None
        self.simairporttype = "X-Plane"
        self.airport_base = os.path.join(DATA_DIR, "managedairport", icao)
        self.runway_exits = {}
        self.takeoff_queues = {}


    def load(self):
        logger.debug(":load: loading super..")
        status = super().load()
        if not status[0]:
            return status
        logger.debug(f":load: ..done. loading complement.. {status}")
        status = self.makeAdditionalAerowayPOIS()
        if not status[0]:
            return status
        logger.debug(f":load: ..done {status}")
        return [True, ":XPAirport::load loaded"]


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
                                        logger.debug(f":loadFromFile: did not load empty line '{line}'")
                                    line = apt_dat.readline()  # next line in apt.dat
                                # Info 4.b
                                logger.info(f":loadFromFile: read {len(self.lines)} lines for {self.name}.")
                                self.loaded = True

                        if(line):  # otherwize we reached the end of file
                            line = apt_dat.readline()  # next line in apt.dat

                    apt_dat.close()

            scenery = scenery_packs.readline()

        scenery_packs.close()
        return [True, "XPAirport::loadFromFile: loaded"]


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
        logger.debug(f":loadRunways: added {len(runways.keys())} runways: {runways.keys()}")
        return [True, "XPAirport::loadRunways loaded"]

    def loadRamps(self):
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
                    ramp.setProp("icao-width", args[0])
                if len(args) > 1:
                    ramp.setProp("operation-type", args[1])
                if len(args) > 2:
                    ramp.setProp("airline", args[2])
            else:
                ramp = None

        self.ramps = ramps
        logger.debug(f":loadRamps: added {len(ramps.keys())} ramps: {ramps.keys()}")
        return [True, "XPAirport::loadRamps loaded"]

    def loadTaxiways(self):
        # Collect 1201 and (102,1204) line codes and create routing network (graph) of taxiways
        # code  LAT          LON          WAY  ID NAME...
        # 1201  25.29549372  051.60759816 both 16 unnamed entity(split)
        def addVertex(aptline):
            args = aptline.content().split()
            return self.taxiways.add_vertex(Vertex(node=args[3], point=Point((float(args[1]), float(args[0]))), usage=[ args[2]], name=" ".join(args[3:])))

        vertexlines = list(filter(lambda x: x.linecode() == 1201, self.lines))
        v = list(map(addVertex, vertexlines))
        logger.debug(f":loadTaxiways: loaded {len(v)} vertices")

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
                    cost = distance(src["geometry"], dst["geometry"])
                    edge = None
                    if len(args) == 5:
                        # args[2] = {oneway|twoway}, args[3] = {runway|taxiway}
                        edge = Edge(src=src, dst=dst, weight=cost, directed=(args[2]=="oneway"), usage=[args[3]], name=args[4])
                    else:
                        edge = Edge(src=src, dst=dst, weight=cost, directed=(args[2]=="oneway"), usage=args[3], name="")
                    if args[2] == "oneway":
                        edge.setColor("#AA4444")
                    self.taxiways.add_edge(edge)
                    edgeCount += 1
                else:
                    logger.debug(":loadTaxiways: not enough params %d %s.", aptline.linecode(), aptline.content())
            elif aptline.linecode() == 1204 and edge:
                args = aptline.content().split()
                if len(args) >= 2:
                    edge.setTag(USAGE_TAG, args[0])
                    edge.setTag(USAGE_TAG, args[1])
                    edgeActiveCount += 1
                else:
                    logger.debug(":loadTaxiways: not enough params %d %s.", aptline.linecode(), aptline.content())
            else:
                edge = False

        self.taxiways.purge()
        # Info 6
        logger.info(":loadTaxiways: added %d nodes, %d edges (%d enhanced).", len(self.taxiways.vert_dict), edgeCount, edgeActiveCount)
        return [True, "XPAirport::loadTaxiways loaded"]

    def loadServiceRoads(self):
        # Collect 1201 and 1206 line codes and create routing network (graph) of service roads
        # 1201  25.29549372  051.60759816 both 16 unnamed entity(split)
        def addVertex(aptline):
            args = aptline.content().split()
            return self.service_roads.add_vertex(Vertex(node=args[3], point=Point((float(args[1]), float(args[0]))), usage=[ args[2]], name=" ".join(args[3:])))

        vertexlines = list(filter(lambda x: x.linecode() == 1201, self.lines))
        v = list(map(addVertex, vertexlines))
        logger.debug(f":loadServiceNetwork: loaded {len(v)} vertices")

        # 1206 107 11 twoway C
        edgeCount = 0   # just for info
        edge = False
        for aptline in self.lines:
            if aptline.linecode() == 1206: # edge for ground vehicle
                args = aptline.content().split()
                if len(args) >= 3:
                    src = self.service_roads.get_vertex(args[0])
                    dst = self.service_roads.get_vertex(args[1])
                    cost = distance(src["geometry"], dst["geometry"])
                    edge = None
                    name = args[4] if len(args) == 5 else ""
                    edge = Edge(src=src, dst=dst, weight=cost, directed=False, usage=["ground"], name=name)
                    # if args[2] == "oneway":
                    #     edge.setColor("#AA4444")
                    self.service_roads.add_edge(edge)
                    edgeCount += 1
                else:
                    logger.debug(":loadServiceNetwork: not enough params %d %s.", aptline.linecode(), aptline.content())
            else:
                edge = False

        self.service_roads.purge()
        # Info 6
        logger.info(":loadServiceNetwork: added %d nodes, %d edges.", len(self.service_roads.vert_dict), edgeCount)
        return [True, "XPAirport::loadServiceNetwork loaded"]


    def loadPOIS(self):
        status = self.loadServiceDestinations()
        if not status[0]:
            return status
        status = self.loadAerowaysPOIS()
        if not status[0]:
            return status
        status = self.loadServicePOIS()
        if not status[0]:
            return status
        logger.debug(":loadPOIS: loaded")
        return [True, "GeoJSONAirport::loadPOIS loaded"]


    def loadServiceDestinations(self):
        # 1400 47.44374472 -122.30463464 88.1 baggage_train 3 Svc Baggage
        # 1401 47.44103438 -122.30382493 0.0 baggage_train Luggage Train Destination South 2
        # @todo: need to map X-Plane service names to ours.
        # X-Plane: baggage_loader, baggage_train, crew_car, crew_ferrari, crew_limo, pushback, fuel_liners, fuel_jets, fuel_props, food, gpu
        # Baggage train have additional param: 0 to 10 if type is baggage_train, 0 if not
        service_destinations = {}
        svc_dest = 0
        svc_park = 0

        for aptline in self.lines:
            if aptline.linecode() in [1400, 1401]:  # service vehicle paarking or destination
                args = aptline.content().split()
                name = " ".join(args[4:])
                svc = ServiceParking(name=name, parking_type=aptline.linecode(), position=(float(args[1]),float(args[0])), orientation=float(args[2]), use=args[3])
                if aptline.linecode() == 1400:
                    svc_park = svc_park + 1
                    svc.setColor("#ffdddd")
                    svc.setProp("location", "parking")
                if aptline.linecode() == 1401:
                    svc_dest = svc_dest + 1
                    svc.setColor("#ddffdd")
                    svc.setProp("location", "destination")
                service_destinations[name] = svc
        self.service_destinations = service_destinations
        logger.debug(":loadServiceDestination: added %d service_destinations (park=%d, dest=%d)" % (len(service_destinations.keys()), svc_park, svc_dest))
        return [True, "XPAirport::loadServiceDestination loaded"]

    def loadAerowaysPOIS(self):
        self.loadGeometries("aeroway-pois.geojson")
        if self.data is not None and self.data["features"] is not None:
            self.data["features"] = FeatureWithProps.betterFeatures(self.data["features"])

        self.aeroway_pois = {}

        if self.data is not None:  # parse runways
            for f in self.data["features"]:
                poi_type = f.getProp(FEATPROP.POI_TYPE.value)
                if poi_type is None:
                    logger.warning(f":loadAerowaysPOIS: feature with no poi type {f}, skipping")
                else:
                    poi_rwy = f.getProp(FEATPROP.RUNWAY.value)
                    if poi_rwy is None:
                        logger.warning(f":loadAerowaysPOIS: poi runway exit has no runway {f}, skipping")
                    else:
                        poi_name = f.getProp(FEATPROP.NAME.value) if f.getProp(FEATPROP.NAME.value) is not None else str(len(self.aeroway_pois))
                        n = poi_type + ":" + poi_rwy + ":" + poi_name
                        f.setProp(FEATPROP.NAME.value, n)
                        self.aeroway_pois[n] = f

            logger.info(":loadAerowaysPOIS: loaded %d features.", len(self.data["features"]))
            self.data = None

        logger.debug(f":loadAerowaysPOIS: added {len(self.aeroway_pois)} points of interest: {self.aeroway_pois.keys()}")
        return [True, "XPAirport::loadAerowaysPOIS loaded"]

    def loadServicePOIS(self):
        self.loadGeometries("service-pois.geojson")
        if self.data is not None and self.data["features"] is not None:
            self.data["features"] = FeatureWithProps.betterFeatures(self.data["features"])

        self.service_pois = {}
        if self.data is not None:  # parse runways
            for f in self.data["features"]:
                poi_type = f.getProp(FEATPROP.POI_TYPE.value)
                if poi_type is None:
                    logger.warning(f":loadServicePOIS: feature with no poi type {f}, skipping")
                else:
                    if poi_type in [POI_TYPE.DEPOT.value, POI_TYPE.REST_AREA.value]:
                        poi_svc = f.getProp(FEATPROP.SERVICE.value)
                        if poi_svc is None:
                            logger.warning(f":loadServicePOIS: poi {poi_type} has no service {f}, skipping")
                        else:
                            poi_name = f.getProp(FEATPROP.NAME.value) if f.getProp(FEATPROP.NAME.value) is not None else str(len(self.service_pois))
                            n = poi_type + ":" + poi_name
                            p = FeatureWithProps(geometry=f["geometry"], properties=f["properties"])
                            p.setProp(FEATPROP.NAME.value, n)
                            self.service_pois[n] = p

            logger.info(":loadServicePOIS: loaded %d features.", len(self.data["features"]))
            self.data = None

        logger.debug(f":loadServicePOIS: added {len(self.service_pois)} points of interest: {self.service_pois.keys()}")
        return [True, "XPAirport::loadServicePOIS loaded"]

    def getAerowayPOI(self, name):
        res = list(filter(lambda f: f.name == name, self.aeroway_pois))
        return res[0] if len(res) == 1 else None

    def getRamp(self, name):
        return self.ramps[name] if name in self.ramps.keys() else None

    def miles(self, airport):
        return distance(self, airport)


    def makeAdditionalAerowayPOIS(self):
        # build additional points and positions

        def makeQueue(line):
            # place TAKEOFF_QUEUE_SIZE points on line
            name = line.getProp("runway")
            q0 = Feature(geometry=Point(line["geometry"]["coordinates"][0]))
            q1 = Feature(geometry=Point(line["geometry"]["coordinates"][-1]))
            rwy = self.procedures.RWYS[name]
            rwypt = rwy.getPoint()
            d0 = distance(q0, rwypt)
            d1 = distance(q1, rwypt)
            (start, end) = (q1, q0) if d0 < d1 else (q0, q1)
            brng = bearing(start, Feature(geometry=Point(line["geometry"]["coordinates"][1])))
            length = distance(start, end)  # approximately
            segment = length / TAKEOFF_QUEUE_SIZE
            self.takeoff_queues[name] = []
            for i in range(TAKEOFF_QUEUE_SIZE):
                f = destination(start, i * segment, brng, {"units": "km"})
                p = FeatureWithProps(geometry=f["geometry"], properties=f["properties"])
                p.setProp(FEATPROP.RUNWAY.value, name)
                p.setProp(FEATPROP.POI_TYPE.value, POI_TYPE.QUEUE_POSITION.value)
                p.setProp(FEATPROP.NAME.value, i)
                self.takeoff_queues[name].append(p)
            # logger.debug(":makeQueue: added %d queue points for %s" % (len(self.takeoff_queues[name]), name))


        def makeRunwayExits(exitpt):
            name = exitpt.getProp("runway")
            rwy = self.procedures.RWYS[name]
            rwypt = rwy.getPoint()
            dist = distance(Feature(geometry=Point(rwypt["geometry"]["coordinates"])), Feature(geometry=Point(exitpt["geometry"]["coordinates"])))
            exitpt.setProp("length", dist)
            # logger.debug(":makeRunwayExits: added exit for %s at %f" % (name, round(dist, 3)))
            if not name in self.runway_exits:
                self.runway_exits[name] = []
            self.runway_exits[name].append(exitpt)


        if self.procedures is None:
            logger.warning(":makeAdditionalAerowayPOIS: procedures not loaded")
            return [False, ":XPAirport::makeAdditionalAerowayPOIS: procedures not loaded"]

        for k in self.aeroway_pois.values():
            pt = k.getProp(FEATPROP.POI_TYPE.value)
            if TAKEOFF_QUEUE_SIZE > 0 and  pt == POI_TYPE.TAKEOFF_QUEUE.value:
                makeQueue(k)
            if pt == POI_TYPE.RUNWAY_EXIT.value:
                makeRunwayExits(k)

        logger.debug(":makeQueue: added %d queue points for %s" % (TAKEOFF_QUEUE_SIZE, self.runway_exits.keys()))
        for name in self.runway_exits.keys():
            self.runway_exits[name] = sorted(self.runway_exits[name], key=lambda f: f["properties"]["length"])
            logger.debug(f":makeRunwayExits: added {len(self.runway_exits[name])} runway exits for {name}")
            # for f in self.runway_exits[name]:
            #     logger.debug(":makeRunwayExits: added %d runway exits for %s at %f" % (len(self.runway_exits[name]), name, f["properties"]["length"]))

        return [True, ":XPAirport::makeAdditionalAerowayPOIS: loaded"]


    def closest_runway_exit(self, runway, dist):
        i = 0
        closest = None
        while closest is None and i < len(self.runway_exits[runway]):
            if dist > self.runway_exits[runway][i]["properties"]["length"]:
                i = i + 1
            else:
                closest = self.runway_exits[runway][i]

        if closest is None:
            closest = self.runway_exits[runway][-1]

        logger.debug(f":closest_runway_exit: runway {runway}, landing: {dist:f}, runway exit at {closest['properties']['length']:f}")
        return closest


    def queue_point(self, runway, qid):
        # no extra checks
        res = list(filter(lambda f: f["properties"][FEATPROP.NAME.value] == qid, self.takeoff_queues[runway]))
        return res[0]

    """
    In Service POI Feature<Point>, property "service" is a list of | separated services, and "poi" is {depot|rest}.
    """
    def getServicePOIs(self, service_name: str):
        sl = []
        for f in self.service_pois.values():
            s = f.getProp(FEATPROP.SERVICE.value)
            if s is not None:
                if s == "*":
                    sl.append(f)
                else:
                    if service_name in s.split(TAG_SEP):
                        sl.append(f)
        return sl

    def getServicePOI(self, name: str):
        return self.service_pois[name] if name in self.service_pois.keys() else None

    # @todo: Add a "closest POI" version for each of those, given the current position, of course:
    def selectServicePOI(self, name: str, service: str):
        ret = self.service_pois[name] if name in self.service_pois.keys() else None
        if ret is not None:
            logger.debug(f":selectServicePOI: found {name}")
            return ret
        if name == POI_TYPE.DEPOT.value:  # keyword for any depot for service
            logger.debug(f":selectServicePOI: trying generic depot")
            return self.selectRandomServiceDepot(service)
        if name in [POI_TYPE.REST_AREA.value, "rest", "parking"]:  # keyword for any rest area/parking for service
            logger.debug(f":selectServicePOI: trying generic rest area")
            return self.selectRandomServiceRestArea(service)

    def getDepots(self, service_name: str):
        return list(filter(lambda f: f.getProp(FEATPROP.POI_TYPE.value) == POI_TYPE.DEPOT.value, self.getServicePOIs(service_name)))

    def getRestAreas(self, service_name: str):
        return list(filter(lambda f: f.getProp(FEATPROP.POI_TYPE.value) == POI_TYPE.REST_AREA.value, self.getServicePOIs(service_name)))

    def selectRandomServiceDepot(self, service: str):
        l = self.getDepots(service)
        if len(l) == 0:
            logger.warning(f":selectRandomServiceDepot: no depot for { service }")
            return None
        return random.choice(l)

    def selectRandomServiceRestArea(self, service: str):
        l = self.getRestAreas(service)
        if len(l) == 0:
            logger.warning(f":selectRandomServiceRestArea: no rest area for { service }")
            return None
        return random.choice(l)

    def getServiceDepot(self, name: str, service_name: str=None):
        dl = self.service_pois if service_name is None else self.getServicePOIs(service_name)
        dn = list(filter(lambda f: f.getProp("name") == name, dl))
        if len(dn) == 0:
            logger.warning(f":getServiceDepot: { name } not found")
            return None
        return dn[0]  # name may not be unique

    def getServiceRestArea(self, name: str, service_name: str=None):
        dl = self.service_pois if service_name is None else self.getServicePOIs(service_name)
        dn = list(filter(lambda f: f.getProp("name") == name, dl))
        if len(dn) == 0:
            logger.warning(f":getServiceRestArea: { name } not found")
            return None
        return dn[0]


