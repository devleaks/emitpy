"""
ManagedAirport loaded from X-Plane configuration and data files
"""
import os.path
import re
import logging
import random

from enum import Enum
from math import inf
from geojson import Point, Polygon, Feature
from turfpy.measurement import distance, destination, bearing

from .airport import AirportBase
from emitpy.graph import Vertex, Edge, USAGE_TAG
from emitpy.geo import Ramp, ServiceParking, Runway, mkPolygon, findFeatures, FeatureWithProps
from emitpy.parameters import DATA_DIR, XPLANE_DIRECTORY
from emitpy.constants import TAKE_OFF_QUEUE_SIZE, FEATPROP, POI_TYPE, TAG_SEP, POI_COMBO, RAMP_TYPE
from emitpy.constants import REDIS_PREFIX, REDIS_DB, ID_SEP
from emitpy.utils import key_path, rejson

logger = logging.getLogger("XPAirport")


# ################################
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


# ################################
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
        self.check_pois = {}
        self.simairporttype = "X-Plane"
        self.airport_base = os.path.join(DATA_DIR, "managedairport", icao)
        self.runway_exits = {}
        self.takeoff_queues = {}
        self.all_pois_combo = {}

    def load(self):
        """
        Loads X-Plane airport from apt.dat definition file.
        Uses same scanning pattern as X-Plane, starting with scenery_packs file.
        First match wins.
        """
        logger.debug(":load: loading super..")
        status = super().load()
        if not status[0]:
            return status
        logger.debug(f":load: ..done. loading complement.. {status}")
        status = self.makeAdditionalAerowayPOIS()
        if not status[0]:
            return status
        logger.debug(f":load: ..done")
        return [True, ":XPAirport::load loaded"]


    def loadFromFile(self):
        """
        Scans scenery_packs collection for apt.dat files.
        Tries to locate manage airport ICAO. If match is found, data lines are loaded.
        """
        SCENERY_PACKS = os.path.join(XPLANE_DIRECTORY, "Custom Scenery", "scenery_packs.ini")
        scenery_packs = open(SCENERY_PACKS, "r")
        scenery = scenery_packs.readline()
        scenery = scenery.strip()

        while not self.loaded and scenery:  # while we have not found our airport and there are more scenery packs
            if re.match("^SCENERY_PACK", scenery, flags=0):
                logger.debug("SCENERY_PACK %s", scenery.rstrip())
                scenery_pack_dir = scenery[13:-1]
                scenery_pack_apt = os.path.join(XPLANE_DIRECTORY, scenery_pack_dir, "Earth nav data", "apt.dat")
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
        """
        Loads runways from apt.dat lines.
        Line format is:
        #     0     1 2 3    4 5 6 7    8            9               10 11  1213141516   17           18              19 20  21222324
        # 100 60.00 1 1 0.25 1 3 0 16L  25.29609337  051.60889908    0  300 2 2 1 0 34R  25.25546269  051.62677745    0  306 3 2 1 0

        :returns:   { description_of_the_return_value }
        :rtype:     { return_type_description }
        """
        runways = {}
        for aptline in self.lines:
            if aptline.linecode() == 100:  # runway
                args = aptline.content().split()
                runway = mkPolygon(float(args[8]), float(args[9]), float(args[17]), float(args[18]), float(args[0]))
                runways[args[7]] = Runway(args[7], float(args[0]), float(args[8]), float(args[9]), float(args[17]), float(args[18]), runway)
                runways[args[16]] = Runway(args[16], float(args[0]), float(args[17]), float(args[18]), float(args[8]), float(args[9]), runway)

        self.runways = runways
        logger.debug(f":loadRunways: added {len(runways.keys())} runways: {runways.keys()}")
        logger.debug(f":loadRunways: pairing..")
        self.pairRunways()
        logger.debug(f":loadRunways: ..paired")
        return [True, "XPAirport::loadRunways loaded"]

    def loadRamps(self):
        """
        Loads ramps from apt.dat lines.
        Line format is:
        # 1300  25.26123160  051.61147754 155.90 gate heavy|jets|turboprops A1
        # 1301 E airline
        # 1202 ignored.

        :returns:   { description_of_the_return_value }
        :rtype:     { return_type_description }
        """
        ramps = {}

        ramp = None
        for aptline in self.lines:
            if aptline.linecode() == 1300: # ramp  name: str, ramptype: str, position: [float], orientation: float, size: str
                args = aptline.content().split()
                name = " ".join(args[5:])
                ramptype = RAMP_TYPE.TIE_DOWN.value  # default
                if args[3] in ["gate"]:  # 1300: “gate”, “hangar”, “misc” or “tie-down”
                    ramptype = RAMP_TYPE.JETWAY.value
                ramp = Ramp(name=name, ramptype=ramptype, position=(float(args[1]),float(args[0])), orientation=float(args[2]), use=args[4])
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
        # for k,r in ramps.items():
        #     print(f"{k},{r['geometry']['coordinates'][1]},{r['geometry']['coordinates'][0]},{r.getProp('orientation')},{r.getProp('sub-type')},{r.getProp('use')},{r.getProp('icao-width')},{r.getProp('operation-type')},{r.getProp('airline')}")
        logger.debug(f":loadRamps: added {len(ramps.keys())} ramps")  # : {ramps.keys()}
        return [True, "XPAirport::loadRamps loaded"]

    def loadTaxiways(self):
        """
        Loads taxiways from apt.dat lines.
        Line format is:
        # code  LAT          LON          WAY  ID NAME...
        # 1201  25.29549372  051.60759816 both 16 unnamed entity(split)

        :returns:   { description_of_the_return_value }
        :rtype:     { return_type_description }
        """
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
        """
        Loads service roads from apt.dat lines.
        Line format is:
        # 1201  25.29549372  051.60759816 both 16 unnamed entity(split)

        :returns:   { description_of_the_return_value }
        :rtype:     { return_type_description }
        """
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
        """
        Loads a Points of Interest from user-supplied GeoJSON FeatureCollection files.
        Each feature in the collection is a Feature<Point> and contains mandatory
        properties to help identify points of interest.

        :returns:   { description_of_the_return_value }
        :rtype:     { return_type_description }
        """
        status = self.loadServiceDestinations()
        if not status[0]:
            return status
        status = self.loadAerowaysPOIS()
        if not status[0]:
            return status
        status = self.loadServicePOIS()
        if not status[0]:
            return status
        status = self.loadCheckpointPOIS()
        if not status[0]:
            return status
        logger.debug(":loadPOIS: loaded")
        return [True, "GeoJSONAirport::loadPOIS loaded"]


    def loadServiceDestinations(self):
        """
        Loads X-Plane ATC/animated traffic service destinations from apt.dat lines.
        Line format is:
        # 1400 47.44374472 -122.30463464 88.1 baggage_train 3 Svc Baggage
        # 1401 47.44103438 -122.30382493 0.0 baggage_train Luggage Train Destination South 2
        # @todo: need to map X-Plane service names to ours.
        # X-Plane: baggage_loader, baggage_train, crew_car, crew_ferrari, crew_limo, pushback, fuel_liners, fuel_jets, fuel_props, food, gpu
        # Baggage train have additional param: 0 to 10 if type is baggage_train, 0 if not

        :returns:   { description_of_the_return_value }
        :rtype:     { return_type_description }
        """
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
        """
        Loads an aeroways points of interest from a user-supplied GeoJSON FeatureCollection file.
        Aeroways POIs help aircraft move on the ground. POIs include:
        - Runway exists
        - Take-off Queue LineString.
        The take-off Queue LineString is used to build a collection of queueing position for takeoffs.
        """
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

            logger.info(":loadAerowaysPOIS: loaded %d features.", len(self.aeroway_pois))
            self.data = None

        logger.debug(f":loadAerowaysPOIS: added {len(self.aeroway_pois)} points of interest: {self.aeroway_pois.keys()}")
        return [True, "XPAirport::loadAerowaysPOIS loaded"]

    def loadServicePOIS(self):
        """
        Loads a service points of interest from a user-supplied GeoJSON FeatureCollection file.
        Service POIs help ground support vehicle move on the ground. POIs include:
        - Depots for services (Fuel, Catering, Water...)
        - Parking and rest areas for inactive ground vehicle
        POIs contain mandatory properties to help identify depot and rest area functions and use.
        """
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
                            p = FeatureWithProps.new(f)
                            p.setProp(FEATPROP.NAME.value, n)
                            self.service_pois[n] = p

            logger.info(":loadServicePOIS: loaded %d features.", len(self.service_pois))
            self.data = None

        logger.debug(f":loadServicePOIS: added {len(self.service_pois)} points of interest: {self.service_pois.keys()}")
        return [True, "XPAirport::loadServicePOIS loaded"]

    def getServicePoisCombo(self, service: str = None):
        """
        Returns a list of (code, description) pairs for all service points of interest.
        """
        l = sorted(self.service_pois.values(), key=lambda x: x.getName())
        if service is not None:
            l = list(filter(lambda f: f.getProp(FEATPROP.SERVICE.value) == service, l))
        a = [(a.getName(), a.getName()) for a in l]
        return a

    def loadCheckpointPOIS(self):
        """
        Loads a checkpoint for missions.
        """
        self.loadGeometries("check-pois.geojson")
        if self.data is not None and self.data["features"] is not None:
            self.data["features"] = FeatureWithProps.betterFeatures(self.data["features"])

        self.check_pois = {}
        if self.data is not None:
            for f in self.data["features"]:
                poi_type = f.getProp(FEATPROP.POI_TYPE.value)
                if poi_type is not None and poi_type == "checkpoint":
                        poi_name = f.getProp(FEATPROP.NAME.value) if f.getProp(FEATPROP.NAME.value) is not None else str(len(self.check_pois))
                        n = poi_type + ":" + poi_name
                        p = FeatureWithProps.new(f)
                        p.setProp(FEATPROP.NAME.value, n)
                        self.check_pois[n] = p
            logger.info(":loadCheckpointPOIS: loaded %d features.", len(self.check_pois))
            self.data = None

        logger.debug(f":loadCheckpointPOIS: added {len(self.check_pois)} points of control: {self.check_pois.keys()}")
        return [True, "XPAirport::loadCheckpointPOIS loaded"]

    def getCheckpointCombo(self):
        """
        Returns a list of (code, description) pairs for all checkpoints.
        """
        l = sorted(self.check_pois.values(),key=lambda x: x.getName())
        a = [(a.getName(), a.getName()) for a in l]
        return a

    def getCheckpoint(self, name, redis = None):
        """
        Gets a named checkpoint.

        :param      name:  The name
        :type       name:  { type_description }
        """
        if redis:
            k = key_path(REDIS_PREFIX.AIRPORT.value, REDIS_PREFIX.GEOJSON.value, REDIS_PREFIX.MISSION.value, name)
            r = rejson(redis=redis, key=k, db=REDIS_DB.REF.value)
            f = FeatureWithProps.new(r)
            return f
        return self.check_pois[name] if name in self.check_pois.keys() else None

    def getControlPoint(self, name):
        """
        Gets a named checkpoint, if not found, get a POI from self.all_pois_combo.

        :param      name:  The name
        :type       name:  { type_description }
        """
        return self.check_pois[name] if name in self.check_pois.keys() else self.getPOIFromCombo(name)

    def getAerowayPOI(self, name):
        """
        Gets a aeroway POI identified by name.

        :param      name:  The name
        :type       name:  { type_description }
        """
        res = list(filter(lambda f: f.name == name, self.aeroway_pois))
        return res[0] if len(res) == 1 else None

    def getRamp(self, name, redis = None):
        """
        Gets the ramp as a X-Plane entity (not a GeoJSON feature)

        :param      name:  The name
        :type       name:  { type_description }
        """
        if redis:
            k = key_path(REDIS_PREFIX.AIRPORT.value, REDIS_PREFIX.GEOJSON.value, REDIS_PREFIX.RAMPS.value, name)
            r = rejson(redis=redis, key=k, db=REDIS_DB.REF.value)
            f = FeatureWithProps.new(r)
            return Ramp(name=f.getProp("name"), ramptype=f.getProp("sub-type"), position=r["geometry"]["coordinates"], orientation=f.getProp("orientation"), use=f.getProp("use"))
        return self.ramps[name] if name in self.ramps.keys() else None

    def miles(self, airport):
        """
        Returns the distance, in nautical miles, from the current (managed) airport to the supplied airport.
        Used to compute bonus milage.

        :param      airport:  The airport
        :type       airport:  { type_description }
        """
        return distance(self, airport)


    def makeAdditionalAerowayPOIS(self):
        """
        Builds additional aeroway POIs Feature<Point> from user-supplied Feature>LineString>.
        """

        def makeQueue(line):
            # place TAKE_OFF_QUEUE_SIZE points on line
            name = line.getProp(FEATPROP.RUNWAY.value)
            q0 = Feature(geometry=Point(line["geometry"]["coordinates"][0]))
            q1 = Feature(geometry=Point(line["geometry"]["coordinates"][-1]))
            rwy = self.procedures.RWYS[name]
            rwypt = rwy.getPoint()
            d0 = distance(q0, rwypt)
            d1 = distance(q1, rwypt)
            (start, end) = (q1, q0) if d0 < d1 else (q0, q1)
            brng = bearing(start, Feature(geometry=Point(line["geometry"]["coordinates"][1])))
            length = distance(start, end)  # approximately
            segment = length / TAKE_OFF_QUEUE_SIZE
            self.takeoff_queues[name] = []
            for i in range(TAKE_OFF_QUEUE_SIZE):
                f = destination(start, i * segment, brng, {"units": "km"})
                p = FeatureWithProps.new(f)
                p.setProp(FEATPROP.RUNWAY.value, name)
                p.setProp(FEATPROP.POI_TYPE.value, POI_TYPE.QUEUE_POSITION.value)
                p.setProp(FEATPROP.NAME.value, i)
                self.takeoff_queues[name].append(p)
            # logger.debug(":makeQueue: added %d queue points for %s" % (len(self.takeoff_queues[name]), name))


        def makeRunwayExits(exitpt):
            name = exitpt.getProp(FEATPROP.RUNWAY.value)
            rwy = self.procedures.RWYS[name]
            rwypt = rwy.getPoint()
            dist = distance(rwypt, exitpt)
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
            if TAKE_OFF_QUEUE_SIZE > 0 and  pt == POI_TYPE.TAKE_OFF_QUEUE.value:
                makeQueue(k)
            if pt == POI_TYPE.RUNWAY_EXIT.value:
                makeRunwayExits(k)

        logger.debug(":makeQueue: added %d queue points for %s" % (TAKE_OFF_QUEUE_SIZE, self.runway_exits.keys()))
        for name in self.runway_exits.keys():
            self.runway_exits[name] = sorted(self.runway_exits[name], key=lambda f: f["properties"]["length"])
            logger.debug(f":makeRunwayExits: added {len(self.runway_exits[name])} runway exits for {name}")
            # for f in self.runway_exits[name]:
            #     logger.debug(":makeRunwayExits: added %d runway exits for %s at %f" % (len(self.runway_exits[name]), name, f["properties"]["length"]))

        return [True, ":XPAirport::makeAdditionalAerowayPOIS: loaded"]


    def closest_runway_exit(self, runway, dist):
        """
        Utility function to located the closest runway exit in front of the plane
        located at dist distance from the runway threshold.

        :param      runway:  The runway
        :type       runway:  { type_description }
        :param      dist:    The distance
        :type       dist:    { type_description }
        """
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
        """
        Returns the takeoff queue position from the runway name and the position in the queue.
        """
        res = list(filter(lambda f: f["properties"][FEATPROP.NAME.value] == qid, self.takeoff_queues[runway]))
        return res[0]

    """
    In Service POI Feature<Point>, property "service" is a list of | separated services, and "poi" is {depot|rest}.
    """
    def getServicePOIs(self, service_name: str):
        """
        Returns a list of POIs for the supplied service.
        """
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

    def getServicePOI(self, name: str, redis = None):
        """
        Returns the named POI.
        """
        if redis:
            k = key_path(REDIS_PREFIX.AIRPORT.value, REDIS_PREFIX.GEOJSON.value, REDIS_PREFIX.GROUNDSUPPORT.value, name)
            r = rejson(redis=redis, key=k, db=REDIS_DB.REF.value)
            f = FeatureWithProps.new(r)
            return f

        return self.service_pois[name] if name in self.service_pois.keys() else None

    def selectServicePOI(self, name: str, service: str, redis = None):
        """
        Returns the named POI if existing, otherwise tries to locate an alternative POI
        for the supplied service.

        :param      name:     The name
        :type       name:     str
        :param      service:  The service
        :type       service:  str
        """
        if name == POI_TYPE.DEPOT.value:  # keyword for any depot for service
            logger.debug(f":selectServicePOI: trying generic depot")
            return self.selectRandomServiceDepot(service, redis)
        if name in [POI_TYPE.REST_AREA.value, "rest", "parking"]:  # keyword for any rest area/parking for service
            logger.debug(f":selectServicePOI: trying generic rest area")
            return self.selectRandomServiceRestArea(service, redis)

        a = name.split(ID_SEP)

        if a[0] == POI_COMBO.RAMP.value:
            return self.getRamp(key_path(*a[1:]), redis)
        if a[0] == POI_COMBO.CHECKPOINT.value:
            return self.getCheckpoint(key_path(*a[1:]), redis)
        if a[0] == POI_COMBO.SERVICE.value:
            return self.getServicePOI(key_path(*a[1:]), redis)


        # logger.debug(f":selectServicePOI: {name} trying service poi..")
        # ret = self.service_pois[name] if name in self.service_pois.keys() else None
        # if ret is None: # if poi in the form ramp:XXX or svc:XXX
        #     logger.debug(f":selectServicePOI: {name} is not a service poi, may be a ramp?")
        #     a = name.split(ID_SEP)
        #     if len(a)>1:
        #         ret = self.ramps[a[1]] if a[1] in self.ramps.keys() else None

        # if ret is not None:
        #     logger.debug(f":selectServicePOI: found {name}")
        #     return ret

    def getNearestPOI(self, poi_list, position: Feature):
        """
        Gets the nearest POI from a list pof POIs and a reference position.

        :param      poi_list:  The poi list
        :type       poi_list:  { type_description }
        :param      position:  The position
        :type       position:  Feature
        """
        if len(poi_list) == 0:
            logger.warning(f":getNearestPOI: no POI in list")
            return None
        if len(poi_list) == 1:
            logger.debug(f":getNearestPOI: one in list, returning {poi_list[0].getProp('name')}")
            return poi_list[0]

        closest = None
        dist = inf
        for p in poi_list:
            d = distance(position, p)
            if d < dist:
                dist = d
                closest = p
        logger.debug(f":getNearestPOI: found {poi_list[0].getProp('name')}")
        return closest

    def getDepots(self, service_name: str, redis = None):
        """
        Get all depot POIs for named service.

        :param      service_name:  The service name
        :type       service_name:  str
        """
        return list(filter(lambda f: f.getProp(FEATPROP.POI_TYPE.value) == POI_TYPE.DEPOT.value, self.getServicePOIs(service_name)))

    def getNearestServiceDepot(self, service_name: str, position: Feature, redis = None):
        """
        Get nearest depot POI for named service.

        :param      service_name:  The service name
        :type       service_name:  str
        """
        return self.getNearestPOI(self.getDepots(service_name), position)

    def getRestAreas(self, service_name: str, redis = None):
        """
        Get all rest area POIs for named service.

        :param      service_name:  The service name
        :type       service_name:  str
        """
        return list(filter(lambda f: f.getProp(FEATPROP.POI_TYPE.value) == POI_TYPE.REST_AREA.value, self.getServicePOIs(service_name)))

    def getNearestServiceRestArea(self, service_name: str, position: Feature, redis = None):
        """
        Get nearest rest area POI for named service.

        :param      service_name:  The service name
        :type       service_name:  str
        """
        return self.getNearestPOI(self.getRestAreas(service_name), position)

    def selectRandomServiceDepot(self, service: str, redis = None):
        """
        Selects a random depot for named service.

        :param      service:  The service
        :type       service:  str
        """
        service = service.lower()
        l = self.getDepots(service)
        if len(l) == 0:
            logger.warning(f":selectRandomServiceDepot: no depot for { service }")
            return None
        return random.choice(l)

    def selectRandomServiceRestArea(self, service: str, redis = None):
        """
        Selects a random service area for named service.

        :param      service:  The service
        :type       service:  str
        """
        service = service.lower()
        l = self.getRestAreas(service)
        if len(l) == 0:
            logger.warning(f":selectRandomServiceRestArea: no rest area for { service }")
            return None
        return random.choice(l)

    def getServiceDepot(self, name: str, service_name: str=None, redis = None):
        """
        Returns the named depot POI if existing, otherwise tries to locate an alternative depot for service.

        :param      name:     The name
        :type       name:     str
        :param      service:  The service
        :type       service:  str
        """
        dl = self.service_pois if service_name is None else self.getServicePOIs(service_name, redis = None)
        dn = list(filter(lambda f: f.getName() == name, dl))
        if len(dn) == 0:
            logger.warning(f":getServiceDepot: { name } not found")
            return None
        return dn[0]  # name may not be unique

    def getServiceRestArea(self, name: str, service_name: str=None, redis = None):
        """
        Returns the named rest area POI if existing, otherwise tries to locate an alternative rest area for service.

        :param      name:     The name
        :type       name:     str
        :param      service:  The service
        :type       service:  str
        """
        dl = self.service_pois if service_name is None else self.getServicePOIs(service_name)
        dn = list(filter(lambda f: f.getName() == name, dl))
        if len(dn) == 0:
            logger.warning(f":getServiceRestArea: { name } not found")
            return None
        return dn[0]

    def getPOIFromCombo(self, combo_name):
        """
        Returns the combo_named point of interest.
        This function is meant to work with poisCombo().

        :param      name:  The name
        :type       name:  { type_description }
        """
        if len(self.all_pois_combo) == 0:  # builds the list
            self.getPOICombo()
        return self.all_pois_combo[combo_name] if combo_name in self.all_pois_combo.keys() else None

    def getPOICombo(self):
        """
        Builds a list of (code, description) of all Points of Interest.
        POIs include ramps, depots, rest areas, checkpoints.
        Original item is retrieved with getPOI
        """
        if len(self.all_pois_combo) > 0:  # builds the list
            return [(v.combo_name, v.display_name) for v in self.all_pois_combo.values()]

        # In the process, we add a .desc attribute to simplify presentation in list
        # Ramps
        for k, v in self.ramps.items():
            v.combo_name = key_path(POI_COMBO.RAMP.value, k)
            v.display_name = "Ramp " + k
            self.all_pois_combo[v.combo_name] = v
        # Checkpoints
        for k, v in self.check_pois.items():
            v.combo_name = key_path(POI_COMBO.CHECKPOINT.value, k)
            v.display_name = "Checkpoint " + k
            self.all_pois_combo[v.combo_name] = v
        # Depots and rest areas
        for k, v in self.service_pois.items():
            v.combo_name = key_path(POI_COMBO.SERVICE.value, k)
            v.display_name = k
            self.all_pois_combo[v.combo_name] = v

        # logger.debug(f":getCombo: {self.all_pois_combo.keys()}")
        return self.getPOICombo()


