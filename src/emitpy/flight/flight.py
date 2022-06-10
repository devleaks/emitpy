import logging
from datetime import datetime, timedelta, timezone

from emitpy.airspace import FlightPlan, FlightPlanRoute
from emitpy.airport import Airport
from emitpy.business import Airline
from emitpy.aircraft import Aircraft
from emitpy.constants import PAYLOAD, FLIGHT_PHASE, FEATPROP, FLIGHT_TIME_FORMAT, ARRIVAL, DEPARTURE
from emitpy.utils import FT
from emitpy.message import Messages, FlightboardMessage

logger = logging.getLogger("Flight")


class Flight(Messages):

    def __init__(self, operator: Airline, number: str, scheduled: datetime, departure: Airport, arrival: Airport, aircraft: Aircraft, linked_flight: 'Flight' = None):
        Messages.__init__(self)
        self.number = number
        self.departure = departure
        self.arrival = arrival
        self.linked_flight = linked_flight
        self.managedAirport = None
        self.scheduled_dt = scheduled
        self.scheduled = scheduled.isoformat()
        self.estimated = None
        self.actual = None
        self.schedule_history = []  # [(timestamp, {ETA|ETD|STA|STD}, datetime)]
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
        self.meta = {
            "departure": {},
            "arrival": {}
        }
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
            "scheduled": self.scheduled,
            "airline": self.operator.getInfo(),
            "departure": self.departure.getInfo(),
            "arrival": self.arrival.getInfo(),
            "aircraft": self.aircraft.getInfo(),
            "icao24": self.aircraft.icao24,
            "callsign": self.aircraft.callsign,
            "flightnumber": self.getName(),
            "codeshare": self.codeshare,
            "ramp": self.ramp.getInfo() if self.ramp is not None else {},
            "runway": self.runway.getInfo() if self.runway is not None else {},  # note: this is the GeoJSON feature, not the RWY procedure
            "is_arrival": self.is_arrival()  # simply useful denormalisation...
            # "metar": self.metar,
            # "meta": self.meta
        }


    def getId(self, use_localtime: bool = False) -> str:
        """
        Standard ICAO name for flight, based on airline, flight number and scheduled takeoff zulu time (of first leg if multiple legs).

        :returns:   The identifier.
        :rtype:     str
        """
        if use_localtime:
            return self.operator.iata + self.number + "-S" + self.scheduled_dt.strftime(FLIGHT_TIME_FORMAT)
        return self.operator.iata + self.number + "-S" + self.scheduled_dt.astimezone(tz=timezone.utc).strftime(FLIGHT_TIME_FORMAT)


    @staticmethod
    def parseId(flight_id):
        """
        Parses IATA flight identifier as built by getId().
        Returns set(flight designator, scheduled time (UTC), airline IATA code, flight number)

        :param      flight_id:  The flight identifier
        :type       flight_id:  { type_description }
        """
        a = flight_id.split("-")
        scheduled_utc = datetime.strptime(a[1], "S" + FLIGHT_TIME_FORMAT)
        return (a[0], scheduled_utc, a[0][0:2], a[2:])

    def getScheduleHistory(self, as_string: bool = False):
        """
        Gets the schedule history.
        """
        if as_string:
            a = []
            for f in self.schedule_history:
                f0 = f[0] if type(f[0]) == str else f[0].isoformat()
                f2 = f[2] if type(f[2]) == str else f[2].isoformat()
                a.append((f0, f[1], f2))
            return a
        return self.schedule_history


    def getName(self) -> str:
        """
        Gets the name.

        :returns:   The name.
        :rtype:     str
        """
        return self.operator.iata + " " + self.number


    def getDisplayName(self) -> str:
        return self.operator.iata + " " + self.number + " " + self.scheduled_dt.strftime("%H:%M")


    def is_arrival(self) -> bool:
        if self.managedAirport is not None:
            return self.arrival.icao == self.managedAirport.icao
        logger.warning(f":is_arrival: no managedAirport, cannot determine")
        return None


    def get_move(self) -> str:
        if self.is_arrival():
            return ARRIVAL
        return DEPARTURE


    def is_departure(self) -> bool:
        if self.managedAirport is not None:
            return self.departure.icao == self.managedAirport.icao
        logger.warning(f":is_departure: no managedAirport, cannot determine")
        return None


    def getRemoteAirport(self) -> Airport:
        return self.departure if self.is_arrival() else self.arrival


    def setLinkedFlight(self, linked_flight: 'Flight') -> None:
        self.linked_flight = linked_flight
        if linked_flight.linked_flight is None:
            linked_flight.linked_flight = self
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
        """
        Cruise altitude in meters.
        """
        return self.flight_level * 100 * FT


    def setRamp(self, ramp):
        name = ramp.getName()
        if name in self.managedAirport.airport.ramps.keys():
            am = self.managedAirport.airport.manager
            reqtime = self.scheduled_dt
            reqend  = reqtime + timedelta(minutes=120)
            if am.ramp_allocator.isAvailable(name, reqtime, reqend):
                res = am.ramp_allocator.book(name, reqtime, reqend, self.getId())
            self.ramp = ramp
            logger.debug(f":setRamp: flight {self.getName()}: ramp {name}")
        else:
            logger.warning(f":setRamp: {name} not found, ramp unchanged")


    def setGate(self, gate):
        """
        For information only. Not used.

        :param      gate:  The gate
        :type       gate:  { type_description }
        """
        self.gate = gate
        logger.debug(f":setGate: flight {self.getName()}: gate {self.gate}")


    def setRWY(self, rwy):
        self.rwy = rwy
        self._setRunway()
        logger.debug(f":setRWY: {self.getName()}: {self.rwy.name}")


    def _setRunway(self, move):
        if self.rwy is not None:
            self.runway = move.getRunway(self.rwy)
            if self.runway is not None:
                name = self.runway.getResourceId()
                # if name[0:2] != "RW":  # add it
                #     logger.debug(f":_setRunway: correcting: RW+{name}")
                #     name = "RW" + name
                am = self.managedAirport.airport.manager
                if name in am.runway_allocator.resources.keys():
                    reqtime = self.scheduled_dt + timedelta(minutes=20)  # time to taxi
                    reqend  = reqtime + timedelta(minutes=5)  # time to take-off + WTC spacing
                    #
                    # @TODO: If not available, should take next availability and "queue"
                    #
                    if am.runway_allocator.isAvailable(name, reqtime, reqend):
                        res = am.runway_allocator.book(name, reqtime, reqend, self.getId())
                    logger.debug(f":_setRunway: flight {self.getName()}: runway {name} ({self.rwy.name})")
                else:
                    logger.warning(f":_setRunway: resource {name} not found, runway unchanged")
                logger.debug(f":_setRunway: {self.getName()}: {name}")
            else:
                logger.warning(f":_setRunway: no runway, runway unchanged")
        else:
            logger.warning(f":_setRunway: no RWY, runway unchanged")


    def loadFlightPlan(self):
        self.flightplan = FlightPlan(managedAirport=self.managedAirport, fromICAO=self.departure.icao, toICAO=self.arrival.icao)

        if not self.flightplan.has_plan():
            logger.warning(":loadFlightPlan: no flight plan in database")

            if self.managedAirport is not None and self.managedAirport.airspace.airways_loaded:  # we loaded airways, we try to build our route
                logger.debug(":loadFlightPlan: trying to build route..")
                self.flightplan = FlightPlanRoute(managedAirport=self.managedAirport.icao, fromICAO=self.departure.icao, toICAO=self.arrival.icao)
                if self.flightplan is not None:
                    if self.flightplan.has_plan():
                        logger.debug(":loadFlightPlan: ..found")
                    else:
                        logger.warning(":loadFlightPlan: ..no route for flight, no plan")

        if not self.flightplan.has_plan():
            logger.warning(":loadFlightPlan: no flight plan, cannot proceed.")
            return

        fplen = len(self.flightplan.nodes())
        logger.debug(":loadFlightPlan: loaded %d waypoints" % fplen)

        if fplen < 4:  # 4 features means 3 nodes (dept, fix, arr) and LineString.
            logger.warning(":loadFlightPlan: flight_plan is too short %d" % fplen)


    def toAirspace(self):
        fpcp = self.flightplan.toAirspace(self.managedAirport.airport.airspace)
        if fpcp[1] > 0:
            logger.warning(":toAirspace: unidentified %d waypoints" % fpcp[1])
        # Sets unique index on flight plan features
        idx = 0
        for f in fpcp[0]:
            f.setProp(FEATPROP.FLIGHT_PLANDB_INDEX.value, idx)
            idx = idx + 1
        logger.debug(f":toAirspace: identified {len(fpcp[0])} waypoints")
        return fpcp[0]


    def setEstimatedTime(self, dt: datetime, info_time: datetime = datetime.now().astimezone()):
        self.estimated = dt
        self.schedule_history.append((dt.isoformat(), "ET", info_time.isoformat()))


    def setActualTime(self, dt: datetime, info_time: datetime = datetime.now().astimezone()):
        self.actual = dt
        self.schedule_history.append((dt.isoformat(), "AT", info_time.isoformat()))


    def plan(self):
        if self.flightplan is None:  # not loaded, trying to load
            self.loadFlightPlan()

        if not self.flightplan.has_plan():  # not found... stops
            logger.warning(":plan: no flight plan")
            return (False, "Flight::plan: no flight plan")

        normplan = self.toAirspace()
        planpts = []

        self.addMessage(FlightboardMessage(flight_id=self.getId(),
                                           is_arrival=self.is_arrival(),
                                           airport=self.getRemoteAirport().icao))

        # ###########################
        # DEPARTURE AND CRUISE
        #
        depapt = self.departure
        rwydep = None

        # RWY
        # self.meta["departure"]["metar"] = depapt.getMetar()
        if depapt.has_rwys():
            rwydep = depapt.selectRWY(self)
            logger.debug(f":plan: departure airport {depapt.icao} using runway {rwydep.name}")
            if self.is_departure():
                self.setRWY(rwydep)
            planpts = rwydep.getRoute()
            planpts[0].setProp("_plan_segment_type", "origin/rwy")
            planpts[0].setProp("_plan_segment_name", depapt.icao+"/"+rwydep.name)
            self.dep_procs = [rwydep]
            self.meta["departure"]["procedure"] = (rwydep.name)
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
                ret = depapt.procedures.getRoute(sid, self.managedAirport.airport.airspace)
                Flight.setProp(ret, "_plan_segment_type", "sid")
                Flight.setProp(ret, "_plan_segment_name", sid.name)
                planpts = planpts + ret
                self.dep_procs = (rwydep, sid)
                self.meta["departure"]["procedure"] = (rwydep.name, sid.name)
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
        # self.meta["arrival"]["metar"] = depapt.getMetar()
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
            self.meta["arrival"]["procedure"] = (rwyarr.name)
        else:  # no star, we are done, we arrive in a straight line
            logger.warning(f":plan: arrival airport {arrapt.icao} has no runway, last point is arrival airport")

        # STAR
        star = None  # used in APPCH
        if arrapt.has_stars() and rwyarr is not None:
            star = arrapt.selectSTAR(rwyarr)
            if star is not None:
                logger.debug(f":plan: {arrapt.icao} using STAR {star.name}")
                ret = arrapt.procedures.getRoute(star, self.managedAirport.airport.airspace)
                Flight.setProp(ret, "_plan_segment_type", "star")
                Flight.setProp(ret, "_plan_segment_name", star.name)
                planpts = planpts[:-1] + ret + [planpts[-1]]  # insert STAR before airport
                self.arr_procs = (rwyarr, star)
                self.meta["arrival"]["procedure"] = (rwyarr.name, star.name)
            else:
                logger.warning(f":plan: arrival airport {arrapt.icao} has no STAR for runway {rwyarr.name}")
        else:  # no star, we are done, we arrive in a straight line
            logger.warning(f":plan: arrival airport {arrapt.icao} has no STAR")

        # APPCH, we found airports with approaches and no STAR
        if arrapt.has_approaches() and rwyarr is not None:
            appch = arrapt.selectApproach(star, rwyarr)  # star won't be used, we can safely pass star=None
            if appch is not None:
                logger.debug(f":plan: {arrapt.icao} using APPCH {appch.name}")
                ret = arrapt.procedures.getRoute(appch, self.managedAirport.airport.airspace)
                Flight.setProp(ret, "_plan_segment_type", "appch")
                Flight.setProp(ret, "_plan_segment_name", appch.name)
                if len(planpts) > 2 and len(ret) > 0 and planpts[-2].id == ret[0].id:
                    logger.debug(f":plan: duplicate end STAR/begin APPCH {ret[0].id} removed")
                    planpts = planpts[:-2] + ret + [planpts[-1]]  # remove last point of STAR
                else:
                    planpts = planpts[:-1] + ret + [planpts[-1]]  # insert APPCH before airport
                self.arr_procs = (rwyarr, star, appch)
                self.meta["arrival"]["procedure"] = (rwyarr.name, star.name if star is not None else "no STAR", appch.name)
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

    def __init__(self, number: str, scheduled: datetime, managedAirport: Airport, origin: Airport, operator: Airline, aircraft: Aircraft, linked_flight: 'Flight' = None):
        Flight.__init__(self, number=number, scheduled=scheduled, departure=origin, arrival=managedAirport.airport, operator=operator, aircraft=aircraft, linked_flight=linked_flight)
        self.managedAirport = managedAirport

    def _setRunway(self):
        super()._setRunway(self.arrival)

    def is_arrival(self) -> bool:
        return True

    def is_departure(self) -> bool:
        return False




class Departure(Flight):

    def __init__(self, number: str, scheduled: datetime, managedAirport: Airport, destination: Airport, operator: Airline, aircraft: Aircraft, linked_flight: 'Flight' = None):
        Flight.__init__(self, number=number, scheduled=scheduled, departure=managedAirport.airport, arrival=destination, operator=operator, aircraft=aircraft, linked_flight=linked_flight)
        self.managedAirport = managedAirport

    def _setRunway(self):
        super()._setRunway(self.departure)

    def is_arrival(self) -> bool:
        return False

    def is_departure(self) -> bool:
        return True
