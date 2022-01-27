import os
import logging
import json
from enum import Enum, auto
from geojson import Feature

from ..airport import Airport
from ..business import Airline
from ..aircraft import Aircraft

from ..parameters import DATA_DIR
from ..constants import MANAGED_AIRPORT, FLIGHTROUTE_DATABASE

logger = logging.getLogger("Flight")


class FLIGHT_PHASE(Enum):
    SCHEDULED = auto()
    UNKNOWN = auto()
    OFFBLOCK = auto()
    PUSHBACK = auto()
    TAXI = auto()
    TAXIHOLD = auto()
    TAKE_OFF = auto()
    TAKEOFF_ROLL = auto()
    ROTATE = auto()
    LIFT_OFF = auto()
    INITIAL_CLIMB = auto()
    CLIMB = auto()
    CRUISE = auto()
    DESCEND = auto()
    APPROACH = auto()
    FINAL = auto()
    LANDING = auto()
    FLARE = auto()
    TOUCH_DOWN = auto()
    ROLL_OUT = auto()
    STOPPED_ON_RWY = auto()
    STOPPED_ON_TAXIWAY = auto()
    ONBLOCK = auto()
    TERMINATED = auto()


class Flight:

    def __init__(self, operator: Airline, number: str, scheduled: str, departure: Airport, arrival: Airport, aircraft: Aircraft):
        self.number = number
        self.departure = departure
        self.arrival = arrival
        self.managedAirport = None
        self.scheduled = scheduled
        self.actual = None
        self.flight_type = "PAX"  # |"CARGO"  # Determined from operator and flight number (for ex. > 5000)
        self.operator = operator
        self.aircraft = aircraft
        self.ramp = None
        self.codeshare = None
        self.phase = FLIGHT_PHASE.SCHEDULED if scheduled else FLIGHT_PHASE.UNKNOWN
        self.flightroute = None
        self.procedure = None


    def setRamp(self, ramp):
        if ramp in self.managedAirport.parkings.keys():
            self.ramp = ramp
            logger.debug("Flight::setRamp: %s" % self.ramp)
        else:
            logger.warning("Flight::setRamp: %s not found" % self.ramp)


    def setGate(self, gate):
        self.gate = gate
        logger.debug("Flight::setGate: %s" % self.gate)


    def loadFlightRoute(self):
        flight = self.departure.icao.lower() + "-" + self.arrival.icao.lower()
        filename = os.path.join(DATA_DIR, MANAGED_AIRPORT, self.managedAirport.icao.upper(), FLIGHTROUTE_DATABASE, flight + ".geojson")
        if os.path.exists(filename):
            file = open(filename, "r")
            self.flightroute = json.load(file)
            file.close()
            logger.debug("Flight::loadFlightRoute: load %d nodes for %s" % (len(self.flightroute["features"]), flight))
        else:
            logger.warning("Flight::loadFlightRoute: file not found %s" % filename)


    def transformFlightRoute(self, route):
        """
        Transform FeatureCollection<Feature<Point>> from FlightPlanDatabase into FeatureCollection<Feature<Vertex>>
        where Vertex in Airspace.
        """
        def isPoint(f):
            return ("geometry" in f) and ("type" in f["geometry"]) and (f["geometry"]["type"] == "Point")

        wpts = []
        errs = 0
        for f in route:
            if isPoint(f):
                fty = f["properties"]["type"] if "type" in f["properties"] else None
                fid = f["properties"]["ident"] if "ident" in f["properties"] else None
                if fid is not None:
                    wid = self.managedAirport.airspace.findControlledPointByName(fid)
                    if len(wid) == 1:
                        v = self.managedAirport.airspace.vert_dict[wid[0]]
                        wpts.append(v)
                        logger.debug("Flight::transformFlightRoute: added %s %s as %s" % (fty, fid, v.id))
                    else:
                        errs = errs + 1
                        logger.warning("Flight::transformFlightRoute: ambiguous ident %s has %d entries" % (fid, len(wid)))
                else:
                    errs = errs + 1
                    logger.warning("Flight::transformFlightRoute: no ident for feature %s" % (fid))
        return (wpts, errs)

    def taxi(self):
        pass

    def plan(self):
        pass

    def fly(self):
        pass


class Arrival(Flight):

    def __init__(self, number: str, scheduled: str, managedAirport: Airport, origin: Airport, operator: Airline, aircraft: Aircraft):
        Flight.__init__(self, number=number, scheduled=scheduled, departure=origin, arrival=managedAirport, operator=operator, aircraft=aircraft)
        self.managedAirport = managedAirport


    def trimFlightRoute(self):
        """
        Remove last point for now, which is arrival airport

        Later algorithm: Create mini graph.
        Add vertex for each point within 100NM (50?) from arrival back to departure.
        Add each STAR+APPCH combination (directed graph) towards RWY.
        Choose shortest path (A*).
        Return:
           Last point in flightplan (ie. trim flight plan to that point)
           STAR
           APPCH
        """
        features = list(filter(lambda f: ("geometry" in f) and ("type" in f["geometry"]) and (f["geometry"]["type"] == "Point"), self.flightroute))
        return features[0:-1]  # remove arrival airport


    def plan(self):
        #
        # LNAV DEPARTURE TO ARRIVAL
        #
        if self.flightroute is None:
            self.loadFlightRoute()
        if len(self.flightroute["features"]) < 4:  # 4 features means 3 nodes (dept, fix, arr) and LineString.
            logger.warning("Arrival::plan: flightroute is too short %d" % len(self.flightroute["features"]))

        arrpts = self.trimFlightRoute()
        rt = self.transformFlightRoute(arrpts)
        if rt[1] > 0 or len(arrpts) != len(rt[0]):
            logger.warning("Arrival::plan: flightroute is too short %d" % len(self.flightroute["features"]))
        else:
            logger.warning("Arrival::plan: route transformed successfully")
            arrpts = rt[0]

        rwy = self.managedAirport.getRunway(self)
        logger.debug("Arrival::plan: runway %s" % rwy.name)
        star = self.managedAirport.getProcedure(self, rwy)
        logger.debug("Arrival::plan: STAR %s" % star.name)
        ret = self.managedAirport.procedures.getRoute(star, self.managedAirport.airspace)
        arrpts = arrpts + ret

        appch = self.managedAirport.getApproach(star, rwy)
        logger.debug("Arrival::plan: APPCH %s" % appch.name)
        ret = self.managedAirport.procedures.getRoute(appch, self.managedAirport.airspace)
        arrpts = arrpts + ret

        arrpts = arrpts + rwy.getRoute()
        self.procedure = (star, appch, rwy)

        i = 0
        for f in arrpts:
            if not isinstance(f, Feature):
                logger.warning("Arrival::plan: not a feature: %d: %s: %s" % (i, type(f), f))
                i = i + 1
        if i == 0:
            logger.warning("Arrival::plan: %d features", len(arrpts))

        self.flightroute = arrpts

        self.taxi()  # Runway exit to Ramp

        return (True, "Arrival::plan: planned")
        # ap = ArrivalPath(arr)
        # pa = ap.mkPath()


class Departure(Flight):

    def __init__(self, number: str, scheduled: str, managedAirport: Airport, destination: Airport, operator: Airline, aircraft: Aircraft):
        Flight.__init__(self, number=number, scheduled=scheduled, departure=managedAirport, arrival=destination, operator=operator, aircraft=aircraft)
        self.managedAirport = managedAirport


    def trimFlightRoute(self):
        """
        Remove first point for now, which is departure airport
        """
        features = list(filter(lambda f: ("geometry" in f) and ("type" in f["geometry"]) and (f["geometry"]["type"] == "Point"), self.flightroute))
        return features[1:]  # remove departure airport


    def plan(self):
        #
        # LNAV DEPARTURE TO ARRIVAL
        #
        if self.flightroute is None:
            self.loadFlightRoute()
        if len(self.flightroute["features"]) < 4:  # 4 features means 3 nodes (dept, fix, arr) and LineString.
            logger.warning("Arrival::plan: flightroute is too short %d" % len(self.flightroute["features"]))

        rwy = self.managedAirport.getRunway(self)
        logger.debug("Departure::plan: runway %s" % rwy.name)
        deppts = rwy.getRoute()

        self.taxi()  # Ramp to runway hold

        sid = self.managedAirport.getProcedure(self, rwy)
        logger.debug("Departure::plan: SID %s" % sid.name)
        ret = self.managedAirport.procedures.getRoute(sid, self.managedAirport.airspace)
        deppts = deppts + ret

        temp = self.trimFlightRoute()
        rt = self.transformFlightRoute(temp)
        if rt[1] > 0 or len(temp) != len(rt[0]):
            logger.warning("Departure::plan: flightroute is too short %d" % len(self.flightroute["features"]))
            deppts = deppts + temp
        else:
            logger.warning("Departure::plan: route transformed successfully")
            deppts = deppts + rt[0]


        self.procedure = (rwy, sid)

        i = 0
        for f in deppts:
            if not isinstance(f, Feature):
                logger.warning("Departure::plan: not a feature: %d: %s: %s" % (i, type(f), f))
                i = i + 1
        if i == 0:
            logger.warning("Departure::plan: %d features", len(deppts))

        self.flightroute = deppts
        return (True, "Departure::plan: planned")
        # dp = DeparturePath(dep)
        # pd = dp.mkPath()
