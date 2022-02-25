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

    def __init__(self, operator: Airline, number: str, scheduled: str, departure: Airport, arrival: Airport, aircraft: Aircraft, linked_flight: 'Flight' = None):
        self.number = number
        self.departure = departure
        self.arrival = arrival
        self.linked_flight = linked_flight
        self.managedAirport = None
        self.scheduled = scheduled
        self.scheduled_dt = datetime.fromisoformat(scheduled)
        self.estimated = None
        self.actual = None
        self.schedule_history = None  # [(timestamp, {ETA|ETD|STA|STD}, datetime)]
        self.operator = operator
        self.aircraft = aircraft
        self.ramp = None
        self.turnaround = None
        self.codeshare = None
        self.phase = FLIGHT_PHASE.SCHEDULED if scheduled else FLIGHT_PHASE.UNKNOWN
        self.flight_level = 0
        self.runway = None
        self.flightplan = None
        self.flightplan_cp = []

        self.flight_type = PAYLOAD.PAX
        try:
            if int(number) > 5000:
                if int(number) > 9900:
                    self.flight_type = PAYLOAD.TECH
                else:
                    self.flight_type = PAYLOAD.CARGO
        except ValueError:
            self.flight_type = PAYLOAD.PAX

        if linked_flight is not None and linked_flight.linked_flight is None:
            linked_flight.setLinkedFlight(self)


    def getId(self) -> str:
        return self.operator.iata + self.number + "-S" + self.scheduled_dt.astimezone(tz=timezone.utc).strftime("%Y%m%d%H%M")


    def getName(self) -> str:
        return self.operator.iata + " " + self.number + " " + self.scheduled_dt.strftime("%H:%M")


    def is_arrival(self) -> bool:
        return self.arrival.icao == self.managedAirport.icao


    def is_departure(self) -> bool:
        return self.departure.icao == self.managedAirport.icao


    def setLinkedFlight(self, linked_flight: 'Flight'):
        self.linked_flight = linked_flight
        logger.debug(":setLinkedFlight: %s linked to %s" % (self.getId(), linked_flight.getId()))


    def setFL(self, flight_level: int):
        self.flight_level = flight_level
        if flight_level <= 100:
            logger.warning(":setFL: %d" % self.flight_level)
        else:
            logger.debug(":setFL: %d" % self.flight_level)


    def setTurnaround(self, turnaround: 'Turnaround'):
        self.turnaround = turnaround


    def getCruiseAltitude(self):
        return self.flight_level * 100 * FT


    def setRamp(self, ramp):
        name = ramp.getProp("name")
        if name in self.managedAirport.ramps.keys():
            self.ramp = ramp
            logger.debug(":setRamp: %s: %s" % (self.getName(), self.ramp.getProp("name")))
        else:
            logger.warning(":setRamp: %s not found" % name)


    def setGate(self, gate):
        self.gate = gate
        logger.debug(":setGate: %s: %s" % (self.getName(), self.gate))


    def setRunway(self, rwy):
        self.runway = rwy
        logger.debug(":setRunway: %s: %s" % (self.getName(), self.runway.name))


    def loadFlightPlan(self):
        self.flightplan = FlightPlan(managedAirport=self.managedAirport.icao, fromICAO=self.departure.icao, toICAO=self.arrival.icao)

        fplen = len(self.flightplan.nodes())
        logger.debug(":loadFlightPlan: loaded %d waypoints" % fplen)

        if fplen < 4:  # 4 features means 3 nodes (dept, fix, arr) and LineString.
            logger.warning(":loadFlightPlan: flight_plan is too short %d" % fplen)


    def toAirspace(self):
        fpcp = self.flightplan.toAirspace(self.managedAirport.airspace)
        if fpcp[1] > 0:
            logger.warning(":toAirspace: unidentified %d waypoints" % fpcp[1])
        logger.debug(":toAirspace: identified %d waypoints" % (len(fpcp[0])))
        return fpcp[0]


    def setEstimatedTime(self, dt: datetime):
        self.estimated = dt
        self.schedule_history.append((datetime.now(), "ET", dt))


    def setActualTime(self, dt: datetime):
        self.actual = dt
        self.schedule_history.append((datetime.now(), "AT", dt))


    def plan(self):
        if self.flightplan is None:
            self.loadFlightPlan()
        normplan = self.toAirspace()
        planpts = []

        # ###########################
        # DEPARTURE AND CRUISE
        #
        depapt = self.departure
        rwydep = None

        # RWY
        if depapt.has_rwys():
            rwydep = depapt.selectRunway(self)
            logger.debug(":plan: departure airport %s using runway %s" % (depapt.icao, rwydep.name))
            if self.is_departure():
                self.setRunway(rwydep)
            planpts = rwydep.getRoute()
            planpts[0].setProp("_plan_segment_type", "origin/rwy")
            planpts[0].setProp("_plan_segment_name", depapt.icao+"/"+rwydep.name)
        else:  # no runway, we leave from airport
            logger.warning(":plan: departure airport %s has no runway, first point is departure airport" % (rwydep.icao))
            planpts = depapt
            planpts[0].setProp("_plan_segment_type", "origin")
            planpts[0].setProp("_plan_segment_name", depapt.icao)

        # SID
        if depapt.has_sids() and rwydep is not None:
            logger.debug(":plan: using procedures for departure airport %s" % depapt.icao)
            sid = depapt.getSID(rwydep)
            if sid is not None:  # inserts it
                logger.debug(":plan: %s using SID %s" % (depapt.icao, sid.name))
                ret = depapt.procedures.getRoute(sid, self.managedAirport.airspace)
                Flight.setProp(ret, "_plan_segment_type", "sid")
                Flight.setProp(ret, "_plan_segment_name", sid.name)
                planpts = planpts + ret
            else:
                logger.warning(":plan: departure airport %s has no SID for %s" % (depapt.icao, rwydep.name))

            normplan = normplan[1:]
            Flight.setProp(normplan, "_plan_segment_type", "cruise")
            Flight.setProp(normplan, "_plan_segment_name", depapt.icao+"-"+self.arrival.icao)
            planpts = planpts + normplan

        else:  # no sid, we go straight
            logger.debug(":plan: departure airport %s has no procedure, flying straight" % depapt.icao)
            ret = normplan[1:]  # remove departure airport and leave cruise
            Flight.setProp(ret, "_plan_segment_type", "cruise")
            Flight.setProp(ret, "_plan_segment_name", depapt.icao+"-"+self.arrival.icao)
            planpts = planpts + ret

        # ###########################
        # ARRIVAL
        #
        arrapt = self.arrival
        rwyarr = None

        # RWY
        if arrapt.has_rwys():
            rwyarr = arrapt.selectRunway(self)
            logger.debug(":plan: arrival airport %s using runway %s" % (arrapt.icao, rwyarr.name))
            if self.is_arrival():
                self.setRunway(rwyarr)
            ret = rwyarr.getRoute()
            Flight.setProp(ret, "_plan_segment_type", "rwy")
            Flight.setProp(ret, "_plan_segment_name", rwyarr.name)
            planpts = planpts[:-1] + ret  # no need to add last point which is arrival airport, we replace it with the precise runway end.
        else:  # no star, we are done, we arrive in a straight line
            logger.warning(":plan: arrival airport %s has no runway, last point is arrival airport" % (arrapt.icao))

        # STAR
        star = None  # used in APPCH
        if arrapt.has_stars() and rwyarr is not None:
            star = arrapt.getSTAR(rwyarr)
            if star is not None:
                logger.debug(":plan: %s using STAR %s" % (arrapt.icao, star.name))
                ret = arrapt.procedures.getRoute(star, self.managedAirport.airspace)
                Flight.setProp(ret, "_plan_segment_type", "star")
                Flight.setProp(ret, "_plan_segment_name", star.name)
                planpts = planpts[:-1] + ret + [planpts[-1]]  # insert STAR before airport
            else:
                logger.warning(":plan: arrival airport %s has no STAR for runway %s" % (arrapt.icao, rwyarr.name))
        else:  # no star, we are done, we arrive in a straight line
            logger.warning(":plan: arrival airport %s has no STAR" % (arrapt.icao))

        # APPCH, we found airports with approaches and no STAR
        if arrapt.has_approaches() and rwyarr is not None:
            appch = arrapt.getApproach(star, rwyarr)  # star won't be used, we can safely pass star=None
            if appch is not None:
                logger.debug(":plan: %s using APPCH %s" % (arrapt.icao, appch.name))
                ret = arrapt.procedures.getRoute(appch, self.managedAirport.airspace)
                Flight.setProp(ret, "_plan_segment_type", "appch")
                Flight.setProp(ret, "_plan_segment_name", appch.name)
                if len(planpts) > 2 and len(ret) > 0 and planpts[-2].id == ret[0].id:
                    logger.debug(":plan: duplicate end STAR/begin APPCH %s removed" % ret[0].id)
                    planpts = planpts[:-2] + ret + [planpts[-1]]  # remove last point of STAR
                else:
                    planpts = planpts[:-1] + ret + [planpts[-1]]  # insert APPCH before airport
            else:
                logger.warning(":plan: arrival airport %s has no APPCH for %s " % (arrapt.icao, rwyarr.name))
        else:
            logger.warning(":plan: arrival airport %s has no APPCH" % (arrapt.icao))

        self.flightplan_cp = planpts
        # printFeatures(self.flightplan_cp, "plan")
        return (True, "Flight::plan: planned")

    @staticmethod
    def setProp(arr: list, propname: str, value: str):
        for a in arr:
            a.setProp(propname, value)


class Arrival(Flight):

    def __init__(self, number: str, scheduled: str, managedAirport: Airport, origin: Airport, operator: Airline, aircraft: Aircraft, linked_flight: 'Flight' = None):
        Flight.__init__(self, number=number, scheduled=scheduled, departure=origin, arrival=managedAirport, operator=operator, aircraft=aircraft, linked_flight=linked_flight)
        self.managedAirport = managedAirport


class Departure(Flight):

    def __init__(self, number: str, scheduled: str, managedAirport: Airport, destination: Airport, operator: Airline, aircraft: Aircraft, linked_flight: 'Flight' = None):
        Flight.__init__(self, number=number, scheduled=scheduled, departure=managedAirport, arrival=destination, operator=operator, aircraft=aircraft, linked_flight=linked_flight)
        self.managedAirport = managedAirport
