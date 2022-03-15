import logging
from datetime import datetime, timezone

from ..airspace import FlightPlan
from ..airport import Airport
from ..business import Airline
from ..aircraft import Aircraft
from ..constants import PAYLOAD, FLIGHT_PHASE, FEATPROP
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
        self.ramp = None              # GeoJSON Feature
        self.runway = None            # GeoJSON Feature
        self.turnaround = None
        self.codeshare = None
        self.phase = FLIGHT_PHASE.SCHEDULED if scheduled else FLIGHT_PHASE.UNKNOWN
        self.flight_level = 0
        self.flightplan = None
        self.flightplan_cp = []
        self.dep_procs = None
        self.arr_procs = None
        self.rwy = None               # RWY object

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


    def __str__(self):
        def airc(ac):
            return ac.actype.typeId + "(" + ac.registration + ")"

        def dproc(a):
            s = ""
            if len(a) > 0:
                e = a[0]
                s = e.name if e is not None else "RW--"
            if len(a) > 1:
                e = a[1]
                s = s + " SID " + (e.name if e is not None else "-")
            return s

        def aproc(a):
            s = ""
            if len(a) > 0:
                e = a[0]
                s = e.name if e is not None else "RW--"
            if len(a) > 2:
                e = a[2]
                s = "APPCH " + (e.name if e is not None else "-") + " " + s
            if len(a) > 1:
                e = a[1]
                s = "STAR " + (e.name if e is not None else "-") + " " + s
            return s


        s = self.getName()
        s = s + f" {self.departure.iata}-{self.arrival.iata} {airc(self.aircraft)} FL{self.flight_level}"
        s = s + f" //DEP {self.departure.icao} {dproc(self.dep_procs)} //ARR {self.arrival.icao} {aproc(self.arr_procs)}"
        return s


    def getInfo(self):
        return {
            "identifier": self.getId(),  # IATA/ICAO flight identifier
            "airline": self.operator.getInfo(),
            "departure": self.departure.getInfo(),
            "arrival": self.arrival.getInfo(),
            "aircraft": self.aircraft.getInfo(),
            "icao24": self.aircraft.icao24,
            "ident": self.aircraft.callsign,
            "flightnumber": self.getName(),
            "codeshare": self.codeshare,
            "ramp": self.ramp.getInfo() if self.ramp is not None else {},
            "runway": self.runway.getInfo() if self.runway is not None else {}  # note: this is the GeoJSON feature, not the RWY procedure
        }


    def getId(self) -> str:
        return self.operator.iata + self.number + "-S" + self.scheduled_dt.astimezone(tz=timezone.utc).strftime("%Y%m%d%H%M")


    def getName(self) -> str:
        return self.operator.iata + " " + self.number

    def getLongName(self) -> str:
        return self.operator.iata + " " + self.number + " " + self.scheduled_dt.strftime("%H:%M")


    def is_arrival(self) -> bool:
        return self.arrival.icao == self.managedAirport.icao


    def is_departure(self) -> bool:
        return self.departure.icao == self.managedAirport.icao


    def setLinkedFlight(self, linked_flight: 'Flight') -> None:
        self.linked_flight = linked_flight
        logger.debug(f":setLinkedFlight: {self.getId()} linked to {linked_flight.getId()}")


    def setFL(self, flight_level: int) -> None:
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
            logger.debug(f":setRamp: flight {self.getName()}: ramp {self.ramp.getProp('name')}")
        else:
            logger.warning(f":setRamp: {name} not found")


    def setGate(self, gate):
        self.gate = gate
        logger.debug(f":setGate: flight {self.getName()}: gate {self.gate}")


    def setRWY(self, rwy):
        self.rwy = rwy
        self._setRunway()
        logger.debug(f":setRunway: {self.getName()}: {self.rwy.name}")


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
        idx = 0
        for f in fpcp[0]:
            f.setProp(FEATPROP.FLIGHT_PLANDB_INDEX.value, idx)
            idx = idx + 1
        logger.debug(f":toAirspace: identified {len(fpcp[0])} waypoints")
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
            rwydep = depapt.selectRWY(self)
            logger.debug(f":plan: departure airport {depapt.icao} using runway {rwydep.name}")
            if self.is_departure():
                self.setRWY(rwydep)
            planpts = rwydep.getRoute()
            planpts[0].setProp("_plan_segment_type", "origin/rwy")
            planpts[0].setProp("_plan_segment_name", depapt.icao+"/"+rwydep.name)
            self.dep_procs = [rwydep]
        else:  # no runway, we leave from airport
            logger.warning(f":plan: departure airport {rwydep.icao} has no runway, first point is departure airport")
            planpts = depapt
            planpts[0].setProp("_plan_segment_type", "origin")
            planpts[0].setProp("_plan_segment_name", depapt.icao)

        # SID
        if depapt.has_sids() and rwydep is not None:
            logger.debug(f":plan: using procedures for departure airport {depapt.icao}")
            sid = depapt.selectSID(rwydep)
            if sid is not None:  # inserts it
                logger.debug(f":plan: {depapt.icao} using SID {sid.name}")
                ret = depapt.procedures.getRoute(sid, self.managedAirport.airspace)
                Flight.setProp(ret, "_plan_segment_type", "sid")
                Flight.setProp(ret, "_plan_segment_name", sid.name)
                planpts = planpts + ret
                self.dep_procs = (rwydep, sid)
            else:
                logger.warning(f":plan: departure airport {depapt.icao} has no SID for {rwydep.name}")

            normplan = normplan[1:]
            Flight.setProp(normplan, "_plan_segment_type", "cruise")
            Flight.setProp(normplan, "_plan_segment_name", depapt.icao+"-"+self.arrival.icao)
            planpts = planpts + normplan

        else:  # no sid, we go straight
            logger.debug(f":plan: departure airport {depapt.icao} has no procedure, flying straight")
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
            rwyarr = arrapt.selectRWY(self)
            logger.debug(f":plan: arrival airport {arrapt.icao} using runway {rwyarr.name}")
            if self.is_arrival():
                self.setRWY(rwyarr)
            ret = rwyarr.getRoute()
            Flight.setProp(ret, "_plan_segment_type", "rwy")
            Flight.setProp(ret, "_plan_segment_name", rwyarr.name)
            planpts = planpts[:-1] + ret  # no need to add last point which is arrival airport, we replace it with the precise runway end.
            self.arr_procs = [rwyarr]
        else:  # no star, we are done, we arrive in a straight line
            logger.warning(f":plan: arrival airport {arrapt.icao} has no runway, last point is arrival airport")

        # STAR
        star = None  # used in APPCH
        if arrapt.has_stars() and rwyarr is not None:
            star = arrapt.selectSTAR(rwyarr)
            if star is not None:
                logger.debug(f":plan: {arrapt.icao} using STAR {star.name}")
                ret = arrapt.procedures.getRoute(star, self.managedAirport.airspace)
                Flight.setProp(ret, "_plan_segment_type", "star")
                Flight.setProp(ret, "_plan_segment_name", star.name)
                planpts = planpts[:-1] + ret + [planpts[-1]]  # insert STAR before airport
                self.arr_procs = (rwyarr, star)
            else:
                logger.warning(f":plan: arrival airport {arrapt.icao} has no STAR for runway {rwyarr.name}")
        else:  # no star, we are done, we arrive in a straight line
            logger.warning(f":plan: arrival airport {arrapt.icao} has no STAR")

        # APPCH, we found airports with approaches and no STAR
        if arrapt.has_approaches() and rwyarr is not None:
            appch = arrapt.selectApproach(star, rwyarr)  # star won't be used, we can safely pass star=None
            if appch is not None:
                logger.debug(f":plan: {arrapt.icao} using APPCH {appch.name}")
                ret = arrapt.procedures.getRoute(appch, self.managedAirport.airspace)
                Flight.setProp(ret, "_plan_segment_type", "appch")
                Flight.setProp(ret, "_plan_segment_name", appch.name)
                if len(planpts) > 2 and len(ret) > 0 and planpts[-2].id == ret[0].id:
                    logger.debug(f":plan: duplicate end STAR/begin APPCH {ret[0].id} removed")
                    planpts = planpts[:-2] + ret + [planpts[-1]]  # remove last point of STAR
                else:
                    planpts = planpts[:-1] + ret + [planpts[-1]]  # insert APPCH before airport
                self.arr_procs = (rwyarr, star, appch)
            else:
                logger.warning(f":plan: arrival airport {arrapt.icao} has no APPCH for {rwyarr.name} ")
        else:
            logger.warning(f":plan: arrival airport {arrapt.icao} has no APPCH")


        idx = 0
        for f in planpts:
            f.setProp(FEATPROP.FLIGHT_PLAN_INDEX.value, idx)
            idx = idx + 1

        self.flightplan_cp = planpts
        # printFeatures(self.flightplan_cp, "plan")
        logger.debug(f":plan: generated {len(self.flightplan_cp)} points")
        return (True, "Flight::plan: planned")

    @staticmethod
    def setProp(arr: list, propname: str, value: str):
        for a in arr:
            a.setProp(propname, value)


class Arrival(Flight):

    def __init__(self, number: str, scheduled: str, managedAirport: Airport, origin: Airport, operator: Airline, aircraft: Aircraft, linked_flight: 'Flight' = None):
        Flight.__init__(self, number=number, scheduled=scheduled, departure=origin, arrival=managedAirport, operator=operator, aircraft=aircraft, linked_flight=linked_flight)
        self.managedAirport = managedAirport

    def _setRunway(self):
        self.runway = self.arrival.getRunway(self.rwy)



class Departure(Flight):

    def __init__(self, number: str, scheduled: str, managedAirport: Airport, destination: Airport, operator: Airline, aircraft: Aircraft, linked_flight: 'Flight' = None):
        Flight.__init__(self, number=number, scheduled=scheduled, departure=managedAirport, arrival=destination, operator=operator, aircraft=aircraft, linked_flight=linked_flight)
        self.managedAirport = managedAirport

    def _setRunway(self):
        self.runway = self.departure.getRunway(self.rwy)

