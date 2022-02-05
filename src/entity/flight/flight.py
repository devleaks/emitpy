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
from ..utils import FT

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
        self.flight_level = 0
        self.runway = None
        self.flightplan = None
        self.flightplan_cp = []
        self.procedure = None   # (RWY, SID), or (STAR, APPCH, RWY)

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
        if flight_level <= 100:
            logger.warning(":setFL: %d" % self.flight_level)
        else:
            logger.debug(":setFL: %d" % self.flight_level)


    def getCruiseAltitude(self):
        return self.flight_level * 100 * FT


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


    def plan(self):
        pass


    @staticmethod
    def setProp(arr: list, propname: str, value: str):
        for a in arr:
            a.setProp(propname, value)


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
        fpcp = self.flightplan.toAirspace(self.managedAirport.airspace)
        if fpcp[1] > 0:
            logger.warning(":loadFlightPlan: unidentified %d waypoints" % fpcp[1])
        logger.debug(":loadFlightPlan: identified %d waypoints, first=%s" % (len(fpcp[0]), fpcp[0][0]))
        return fpcp[0][0:-1]  # remove arrival airport


    def plan(self):
        #
        # LNAV DEPARTURE TO ARRIVAL
        #
        if self.flightplan is None:
            self.loadFlightPlan()

        arrpts = self.trimFlightPlan()
        arrpts[0].setProp("_plan_segment_type", "origin")
        arrpts[0].setProp("_plan_segment_name", self.departure.icao)
        Flight.setProp(arrpts[1:], "_plan_segment_type", "cruise")
        Flight.setProp(arrpts[1:], "_plan_segment_name", self.departure.icao+"-"+self.arrival.icao)

        rwy = self.managedAirport.selectRunway(self)
        self.runway = rwy
        logger.debug(":plan: runway %s" % rwy.name)

        star = self.managedAirport.getProcedure(self, rwy)
        logger.debug(":plan: STAR %s" % star.name)
        ret = self.managedAirport.procedures.getRoute(star, self.managedAirport.airspace)
        Flight.setProp(ret, "_plan_segment_type", "star")
        Flight.setProp(ret, "_plan_segment_name", star.name)
        arrpts = arrpts + ret

        appch = self.managedAirport.getApproach(star, rwy)
        logger.debug(":plan: APPCH %s" % appch.name)
        ret = self.managedAirport.procedures.getRoute(appch, self.managedAirport.airspace)
        Flight.setProp(ret, "_plan_segment_type", "appch")
        Flight.setProp(ret, "_plan_segment_name", appch.name)
        arrpts = arrpts + ret

        ret = rwy.getRoute()
        Flight.setProp(ret, "_plan_segment_type", "rwy")
        Flight.setProp(ret, "_plan_segment_name", rwy.name)
        arrpts = arrpts + ret

        self.procedure = (star, appch, rwy)
        self.flightplan_cp = arrpts
        return (True, "Arrival::plan: planned")


class Departure(Flight):

    def __init__(self, number: str, scheduled: str, managedAirport: Airport, destination: Airport, operator: Airline, aircraft: Aircraft):
        Flight.__init__(self, number=number, scheduled=scheduled, departure=managedAirport, arrival=destination, operator=operator, aircraft=aircraft)
        self.managedAirport = managedAirport


    def trimFlightPlan(self):
        """
        Remove first point for now, which is departure airport
        """
        fpcp = self.flightplan.toAirspace(self.managedAirport.airspace)
        if fpcp[1] > 0:
            logger.warning(":loadFlightPlan: unidentified %d waypoints" % fpcp[1])
        logger.debug(":loadFlightPlan: identified %d waypoints, last=%s" % (len(fpcp[0]), fpcp[0][-1]))
        return fpcp[0][1:]  # remove departure airport


    def plan(self):
        #
        # LNAV DEPARTURE TO ARRIVAL
        #
        if self.flightplan is None:
            self.loadFlightPlan()

        rwy = self.managedAirport.selectRunway(self)
        self.runway = rwy
        logger.debug(":plan: runway %s" % rwy.name)
        deppts = rwy.getRoute()
        Flight.setProp(deppts, "_plan_segment_type", "rwy")
        Flight.setProp(deppts, "_plan_segment_name", rwy.name)

        sid = self.managedAirport.getProcedure(self, rwy)
        logger.debug(":plan: SID %s" % sid.name)
        ret = self.managedAirport.procedures.getRoute(sid, self.managedAirport.airspace)
        Flight.setProp(ret, "_plan_segment_type", "sid")
        Flight.setProp(ret, "_plan_segment_name", sid.name)
        deppts = deppts + ret

        plan = self.trimFlightPlan()
        Flight.setProp(plan, "_plan_segment_type", "cruise")
        Flight.setProp(plan, "_plan_segment_name", self.departure.icao+"-"+self.arrival.icao)
        plan[-1].setProp("_plan_segment_type", "destination")
        plan[-1].setProp("_plan_segment_name", self.arrival.icao)
        deppts = deppts + plan

        self.procedure = (rwy, sid)
        self.flightplan_cp = deppts
        return (True, "Departure::plan: planned")
