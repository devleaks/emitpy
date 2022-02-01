import os
import logging
import json
from enum import Enum, auto
from geojson import Feature

from ..airspace import FlightPlan
from ..airport import Airport
from ..business import Airline
from ..aircraft import Aircraft
from ..constants import PAYLOAD

logger = logging.getLogger("Flight")


class FLIGHT_PHASE(Enum):
    OFFBLOCK = "OFFBLOCK"
    PUSHBACK = "PUSHBACK"
    TAXI = "TAXI"
    TAXIHOLD = "TAXIHOLD"
    TAKEOFF_HOLD = "TAXIHOLD"
    TAKE_OFF = "TAKE_OFF"
    TAKEOFF_ROLL = "TAKEOFF_ROLL"
    ROTATE = "ROTATE"
    LIFT_OFF = "LIFT_OFF"
    INITIAL_CLIMB = "INITIAL_CLIMB"
    CLIMB = "CLIMB"
    CRUISE = "CRUISE"
    DESCEND = "DESCEND"
    APPROACH = "APPROACH"
    FINAL = "FINAL"
    LANDING = "LANDING"
    FLARE = "FLARE"
    TOUCH_DOWN = "TOUCH_DOWN"
    ROLL_OUT = "ROLL_OUT"
    STOPPED_ON_RWY = "STOPPED_ON_RWY"
    RUNWAY_EXIT = "RUNWAY_EXIT"
    STOPPED_ON_TAXIWAY = "STOPPED_ON_TAXIWAY"
    PARKING = "PARKING"
    ONBLOCK = "ONBLOCK"
    SCHEDULED = "SCHEDULED"
    TERMINATED = "TERMINATED"
    CANCELLED = "CANCELLED"
    TOWED = "TOWED"
    UNKNOWN = "UNKNOWN"


class Flight:

    def __init__(self, operator: Airline, number: str, scheduled: str, departure: Airport, arrival: Airport, aircraft: Aircraft):
        self.number = number
        self.departure = departure
        self.arrival = arrival
        self.managedAirport = None
        self.scheduled = scheduled
        self.actual = None
        self.operator = operator
        self.aircraft = aircraft
        self.ramp = None
        self.codeshare = None
        self.phase = FLIGHT_PHASE.SCHEDULED if scheduled else FLIGHT_PHASE.UNKNOWN
        self.flightplan = None
        self.flight_level = 0
        self.flightplan_features = []
        self.flightplan_cp = []
        self.procedure = None

        self.flight_type = PAYLOAD.PAX
        try:
            if int(number) > 5000:
                if int(number) > 9900:
                    self.flight_type = PAYLOAD.TECH
                else:
                    self.flight_type = PAYLOAD.CARGO
        except ValueError:
            self.flight_type = PAYLOAD.PAX

    def setFL(self, flight_level: int):
        self.flight_level = flight_level
        logger.debug(":setFL: %d" % self.flight_level)


    def setRamp(self, ramp):
        if ramp in self.managedAirport.parkings.keys():
            self.ramp = ramp
            logger.debug(":setRamp: %s" % self.ramp)
        else:
            logger.warning(":setRamp: %s not found" % self.ramp)


    def setGate(self, gate):
        self.gate = gate
        logger.debug(":setGate: %s" % self.gate)


    def loadFlightPlan(self):
        self.flightplan = FlightPlan(managedAirport=self.managedAirport.icao, fromICAO=self.departure.icao, toICAO=self.arrival.icao)

        fplen = len(self.flightplan.nodes())
        logger.debug(":loadFlightPlan: loaded %d waypoints" % fplen)

        if fplen < 4:  # 4 features means 3 nodes (dept, fix, arr) and LineString.
            logger.warning(":loadFlightPlan: flight_plan is too short %d" % fplen)

        temp = self.flightplan.toAirspace(self.managedAirport.airspace)
        self.flightplan_cp = temp[0]
        if temp[1] > 0:
            logger.warning(":loadFlightPlan: unidentified %d waypoints" % temp[1])
        logger.debug(":loadFlightPlan: identified %d waypoints" % len(self.flightplan_cp))


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


    def trimFlightPlan(self):
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
        # @should check that last point is arrival airport, in case we could not get its ControlledPoint in conversion...
        return self.flightplan_cp[0:-1]  # remove arrival airport


    def plan(self):
        #
        # LNAV DEPARTURE TO ARRIVAL
        #
        if self.flightplan is None:
            self.loadFlightPlan()

        arrpts = self.trimFlightPlan()

        rwy = self.managedAirport.getRunway(self)
        logger.debug(":plan: runway %s" % rwy.name)
        star = self.managedAirport.getProcedure(self, rwy)

        logger.debug(":plan: STAR %s" % star.name)
        ret = self.managedAirport.procedures.getRoute(star, self.managedAirport.airspace)
        arrpts = arrpts + ret

        appch = self.managedAirport.getApproach(star, rwy)
        logger.debug(":plan: APPCH %s" % appch.name)
        ret = self.managedAirport.procedures.getRoute(appch, self.managedAirport.airspace)
        arrpts = arrpts + ret

        arrpts = arrpts + rwy.getRoute()

        self.procedure = (star, appch, rwy)
        self.flightplan_cp = arrpts

        self.flightplan.vnav(isArrival=True, ac=self.aircraft)

        self.taxi()  # Runway exit to Ramp

        return (True, "Arrival::plan: planned")
        # ap = ArrivalPath(arr)
        # pa = ap.mkPath()


class Departure(Flight):

    def __init__(self, number: str, scheduled: str, managedAirport: Airport, destination: Airport, operator: Airline, aircraft: Aircraft):
        Flight.__init__(self, number=number, scheduled=scheduled, departure=managedAirport, arrival=destination, operator=operator, aircraft=aircraft)
        self.managedAirport = managedAirport


    def trimFlightPlan(self):
        """
        Remove first point for now, which is departure airport
        """
        return self.flightplan_cp[1:]  # remove departure airport


    def plan(self):
        #
        # LNAV DEPARTURE TO ARRIVAL
        #
        if self.flightplan is None:
            self.loadFlightPlan()

        rwy = self.managedAirport.getRunway(self)
        logger.debug(":plan: runway %s" % rwy.name)
        deppts = rwy.getRoute()

        self.taxi()  # Ramp to runway hold

        sid = self.managedAirport.getProcedure(self, rwy)
        logger.debug(":plan: SID %s" % sid.name)
        ret = self.managedAirport.procedures.getRoute(sid, self.managedAirport.airspace)
        deppts = deppts + ret

        temp = self.trimFlightPlan()
        deppts = deppts + temp

        self.procedure = (rwy, sid)
        self.flightplan = deppts

        return (True, "Departure::plan: planned")
        # dp = DeparturePath(dep)
        # pd = dp.mkPath()
