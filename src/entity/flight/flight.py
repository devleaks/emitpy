import logging
from datetime import datetime, timezone

from ..airspace import FlightPlan
from ..airport import Airport
from ..business import Airline
from ..aircraft import Aircraft
from ..constants import PAYLOAD, FLIGHT_PHASE
from ..utils import FT

logger = logging.getLogger("Flight")


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


    def getId(self) -> str:
        s = datetime.fromisoformat(self.scheduled)
        return self.operator.iata + self.number + "S" + s.astimezone(tz=timezone.utc).isoformat()


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


    def trimFlightPlan(self, has_procedures=True):
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
        return fpcp[0][1:-1] if has_procedures else fpcp[0][0:-1] # remove arrival airport


    def plan(self):
        #
        # LNAV DEPARTURE TO ARRIVAL
        #
        if self.flightplan is None:
            self.loadFlightPlan()

        if self.departure.has_procedures():
            logger.debug(":plan: using procedures for departure airport %s" % self.departure.icao)
            # Departure
            rwydep = self.departure.selectRunway(self)
            logger.debug(":plan: runway %s" % rwydep.name)
            arrpts = rwydep.getRoute()
            arrpts[0].setProp("_plan_segment_type", "origin")
            arrpts[0].setProp("_plan_segment_name", self.departure.icao)

            # SID
            sid = self.departure.getOtherProcedure(self, rwydep)  # !!
            if sid is not None:
                logger.debug(":plan: SID %s" % sid.name)
                ret = self.departure.procedures.getRoute(sid, self.managedAirport.airspace)
                Flight.setProp(ret, "_plan_segment_type", "sid")
                Flight.setProp(ret, "_plan_segment_name", sid.name)
                arrpts = arrpts + ret
            else:
                logger.warning(":plan: no SID for %s %s" % (self.departure.icao, rwydep.name))
        else:
            logger.debug(":plan: departure airport %s has no procedure" % self.departure.icao)
            if self.flightplan is None:
                self.loadFlightPlan()

            arrpts = self.trimFlightPlan()
            arrpts[0].setProp("_plan_segment_type", "origin")
            arrpts[0].setProp("_plan_segment_name", self.departure.icao)

        # Cruise
        ret = self.trimFlightPlan()
        Flight.setProp(ret, "_plan_segment_type", "cruise")
        Flight.setProp(ret, "_plan_segment_name", self.departure.icao+"-"+self.arrival.icao)
        arrpts = arrpts + ret

        # STAR
        rwy = self.managedAirport.selectRunway(self)
        self.runway = rwy
        logger.debug(":plan: runway %s" % rwy.name)

        star = self.managedAirport.getProcedure(self, rwy)
        if star is not None:
            logger.debug(":plan: STAR %s" % star.name)
            ret = self.managedAirport.procedures.getRoute(star, self.managedAirport.airspace)
            Flight.setProp(ret, "_plan_segment_type", "star")
            Flight.setProp(ret, "_plan_segment_name", star.name)
            arrpts = arrpts + ret
        else:
            logger.warning(":plan: no STAR for %s %s" % (self.managedAirport.icao, rwy.name))

        # APPCH
        appch = self.managedAirport.getApproach(star, rwy)
        if appch is not None:
            logger.debug(":plan: APPCH %s" % appch.name)
            ret = self.managedAirport.procedures.getRoute(appch, self.managedAirport.airspace)
            Flight.setProp(ret, "_plan_segment_type", "appch")
            Flight.setProp(ret, "_plan_segment_name", appch.name)
        else:
            logger.warning(":plan: no APPCH for %s %s" % (self.managedAirport.icao, rwy.name))

        if arrpts[-1].id == ret[0].id:
            logger.debug(":plan: duplicate end STAR/begin APPCH %s removed" % ret[0].id)
            arrpts = arrpts[:-1] + ret  # remove last point of STAR
        else:
            arrpts = arrpts + ret

        # RWY
        ret = rwy.getRoute()
        Flight.setProp(ret, "_plan_segment_type", "rwy")
        Flight.setProp(ret, "_plan_segment_name", rwy.name)
        arrpts = arrpts + ret

        self.procedure = (star, appch, rwy)
        self.flightplan_cp = arrpts
        # printFeatures(self.flightplan_cp, "plan")
        return (True, "Arrival::plan: planned")


class Departure(Flight):

    def __init__(self, number: str, scheduled: str, managedAirport: Airport, destination: Airport, operator: Airline, aircraft: Aircraft):
        Flight.__init__(self, number=number, scheduled=scheduled, departure=managedAirport, arrival=destination, operator=operator, aircraft=aircraft)
        self.managedAirport = managedAirport


    def trimFlightPlan(self, has_procedures=True):
        """
        Remove first point for now, which is departure airport
        """
        fpcp = self.flightplan.toAirspace(self.managedAirport.airspace)
        if fpcp[1] > 0:
            logger.warning(":loadFlightPlan: unidentified %d waypoints" % fpcp[1])
        logger.debug(":loadFlightPlan: identified %d waypoints, last=%s" % (len(fpcp[0]), fpcp[0][-1]))
        return fpcp[0][1:-1] if has_procedures else fpcp[0][1:]  # remove departure airport


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

        # SID
        sid = self.managedAirport.getProcedure(self, rwy)
        if sid is not None:
            logger.debug(":plan: SID %s" % sid.name)
            ret = self.managedAirport.procedures.getRoute(sid, self.managedAirport.airspace)
            Flight.setProp(ret, "_plan_segment_type", "sid")
            Flight.setProp(ret, "_plan_segment_name", sid.name)
            deppts = deppts + ret
        else:
            logger.warning(":plan: no SID for %s %s" % (self.managedAirport.icao, rwy.name))

        # CRUISE
        plan = self.trimFlightPlan()
        Flight.setProp(plan, "_plan_segment_type", "cruise")
        Flight.setProp(plan, "_plan_segment_name", self.departure.icao+"-"+self.arrival.icao)
        deppts = deppts + plan

        if self.arrival.has_procedures():
            logger.debug(":plan: using procedures for arrival airport %s" % self.arrival.icao)
            # STAR
            rwyarr = self.arrival.selectRunway(self)
            star = self.arrival.getOtherProcedure(self, rwyarr)  # !!
            if star is not None:
                logger.debug(":plan: STAR %s" % star.name)
                ret = self.managedAirport.procedures.getRoute(star, self.managedAirport.airspace)
                Flight.setProp(ret, "_plan_segment_type", "star")
                Flight.setProp(ret, "_plan_segment_name", star.name)
                deppts = deppts + ret
            else:
                logger.warning(":plan: no STAR for %s %s" % (self.arrival.icao, rwyarr.name))

            # APPCH
            appch = self.arrival.getApproach(star, rwyarr)
            if appch is not None:
                logger.debug(":plan: APPCH %s" % appch.name)
                ret = self.arrival.procedures.getRoute(appch, self.managedAirport.airspace)
                Flight.setProp(ret, "_plan_segment_type", "appch")
                Flight.setProp(ret, "_plan_segment_name", appch.name)
            else:
                logger.warning(":plan: no STAR for %s %s" % (self.arrival.icao, rwyarr.name))

            if deppts[-1].id == ret[0].id:
                logger.debug(":plan: duplicate end STAR/begin APPCH %s removed" % ret[0].id)
                deppts = deppts[:-1] + ret  # remove last point of STAR
            else:
                deppts = deppts + ret

            ret = rwyarr.getRoute()
            Flight.setProp(ret, "_plan_segment_type", "rwy")
            Flight.setProp(ret, "_plan_segment_name", rwyarr.name)
            deppts = deppts + ret
        else:
            logger.debug(":plan: arrival airport %s has no procedure" % self.arrival.icao)
            plan[-1].setProp("_plan_segment_type", "destination")
            plan[-1].setProp("_plan_segment_name", self.arrival.icao)

        # Arrival
        plan[-1].setProp("_plan_segment_type", "destination")
        plan[-1].setProp("_plan_segment_name", self.arrival.icao)
        deppts = deppts + plan

        self.procedure = (rwy, sid)
        self.flightplan_cp = deppts
        # printFeatures(self.flightplan_cp, "plan")
        return (True, "Departure::plan: planned")
