# Everything Flight
import logging
from datetime import datetime, timedelta, timezone

from emitpy.airspace import FlightRoute
from emitpy.airport import Airport
from emitpy.business import Airline
from emitpy.aircraft import Aircraft
from emitpy.constants import PAYLOAD, FLIGHT_PHASE, FEATPROP, FLIGHT_TIME_FORMAT, ARRIVAL, DEPARTURE, RWY_ARRIVAL_SLOT, RWY_DEPARTURE_SLOT
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
        self.flightroute = None
        self.flightplan_wpts = []
        self.dep_procs = None
        self.arr_procs = None
        self.rwy = None               # RWY object
        self.meta = {
            "departure": {},
            "arrival": {}
        }
        self.flight_type = PAYLOAD.PAX
        self.load_factor = 1.0        # 100% capacity, estimated, both passengers and cargo.

        try:
            if int(number) > 5000:
                if int(number) > 9900:
                    self.flight_type = PAYLOAD.TECH
                else:
                    self.flight_type = PAYLOAD.CARGO
        except ValueError:
            self.flight_type = PAYLOAD.PAX

        if linked_flight is not None and linked_flight.linked_flight is None:
            linked_flight.setLinkedFlight(self) # will do self.setLinkedFlight(linked_flight)

        self.aircraft.setCallsign(self.operator.icao + self.number)  # default


    @staticmethod
    def setProp(arr: list, propname: str, value: str):
        for a in arr:
            a.setProp(propname, value)


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
        # Should check if already defined and different
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


    def setLoadFactor(self, load_factor: float):
        if load_factor >= 0 and load_factor <= 2:
            self.load_factor = load_factor
        else:
            logger.warning(f":setLoadFactor: invalid load factor {load_factor} ∉ [0,2]")


    def setFlightService(self, flight_service: 'FlightService'):
        self.turnaround = flight_service


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
                    reqduration = RWY_DEPARTURE_SLOT if self.is_departure() else RWY_ARRIVAL_SLOT
                    reqend  = reqtime + timedelta(seconds=reqduration)  # time to take-off + WTC spacing
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


    def makeFlightRoute(self):
        self.flightroute = FlightRoute(managedAirport=self.managedAirport, fromICAO=self.departure.icao, toICAO=self.arrival.icao)

        if not self.flightroute.has_route():
            logger.warning(":makeFlightRoute: no flight route, cannot proceed.")
            return

        fplen = len(self.flightroute.nodes())
        if fplen < 4:  # 4 features means 3 nodes (dept, fix, arr) and LineString.
            logger.warning(":makeFlightRoute: flight route is too short %d" % fplen)
        logger.debug(":makeFlightRoute: loaded %d waypoints" % fplen)


    def printFlightRoute(self):
        if self.flightroute is None or not self.flightroute.has_route():
            logger.warning(":printFlightRoute: no flight route")
            return
        return self.flightroute.print()

    def setEstimatedTime(self, dt: datetime, info_time: datetime = datetime.now().astimezone()):
        self.estimated = dt
        self.schedule_history.append((dt.isoformat(), "ET", info_time.isoformat()))


    def setActualTime(self, dt: datetime, info_time: datetime = datetime.now().astimezone()):
        self.actual = dt
        self.schedule_history.append((dt.isoformat(), "AT", info_time.isoformat()))


    def plan(self):
        if self.flightroute is None:  # not loaded, trying to load
            self.makeFlightRoute()

        if not self.flightroute.has_route():  # not found... stops
            logger.warning(":plan: no flight route")
            return (False, "Flight::plan: no flight route")

        normplan = self.flightroute.route()
        waypoints = []

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
            waypoints = rwydep.getRoute()
            waypoints[0].setProp("_plan_segment_type", "origin/rwy")
            waypoints[0].setProp("_plan_segment_name", depapt.icao+"/"+rwydep.name)
            self.dep_procs = [rwydep]
            self.meta["departure"]["procedure"] = (rwydep.name)
        else:  # no runway, we leave from airport
            logger.warning(f":plan: departure airport {rwydep.icao} has no runway, first point is departure airport")
            waypoints = depapt
            waypoints[0].setProp("_plan_segment_type", "origin")
            waypoints[0].setProp("_plan_segment_name", depapt.icao)

        # SID
        if depapt.has_sids() and rwydep is not None:
            logger.debug(f":plan: using procedures for departure airport {depapt.icao}")
            #sid = depapt.selectSID(rwydep)
            print(depapt.procedures.SIDS["RW26R"].keys())
            sid = depapt.procedures.SIDS["RW26R"]["SODE2P"]
            if sid is not None:  # inserts it
                logger.debug(f":plan: {depapt.icao} using SID {sid.name}")
                ret = depapt.procedures.getRoute(sid, self.managedAirport.airport.airspace)
                Flight.setProp(ret, "_plan_segment_type", "sid")
                Flight.setProp(ret, "_plan_segment_name", sid.name)
                waypoints = waypoints + ret
                self.dep_procs = (rwydep, sid)
                self.meta["departure"]["procedure"] = (rwydep.name, sid.name)
            else:
                logger.warning(f":plan: departure airport {depapt.icao} has no SID for {rwydep.name}")

            normplan = normplan[1:]
            Flight.setProp(normplan, "_plan_segment_type", "cruise")
            Flight.setProp(normplan, "_plan_segment_name", depapt.icao+"-"+self.arrival.icao)
            waypoints = waypoints + normplan

        else:  # no sid, we go straight
            logger.debug(f":plan: departure airport {depapt.icao} has no procedure, flying straight")
            ret = normplan[1:]  # remove departure airport and leave cruise
            Flight.setProp(ret, "_plan_segment_type", "cruise")
            Flight.setProp(ret, "_plan_segment_name", depapt.icao+"-"+self.arrival.icao)
            waypoints = waypoints + ret

        # ###########################
        # ARRIVAL
        #
        arrapt = self.arrival
        rwyarr = None

        # RWY
        # self.meta["arrival"]["metar"] = depapt.getMetar()
        if arrapt.has_rwys():
            rwyarr = arrapt.operational_rwys["RW34L"]

            logger.debug(f":plan: arrival airport {arrapt.icao} using runway {rwyarr.name}")
            if self.is_arrival():
                self.setRWY(rwyarr)
            ret = rwyarr.getRoute()
            Flight.setProp(ret, "_plan_segment_type", "rwy")
            Flight.setProp(ret, "_plan_segment_name", rwyarr.name)
            waypoints = waypoints[:-1] + ret  # no need to add last point which is arrival airport, we replace it with the precise runway end.
            self.arr_procs = [rwyarr]
            self.meta["arrival"]["procedure"] = (rwyarr.name)
        else:  # no star, we are done, we arrive in a straight line
            logger.warning(f":plan: arrival airport {arrapt.icao} has no runway, last point is arrival airport")

        # STAR
        star = None  # used in APPCH
        if arrapt.has_stars() and rwyarr is not None:
            # star = arrapt.selectSTAR(rwyarr)
            star = arrapt.procedures.STARS["RW34L"]["BAYA1L"]

            if star is not None:
                logger.debug(f":plan: {arrapt.icao} using STAR {star.name}")
                ret = arrapt.procedures.getRoute(star, self.managedAirport.airport.airspace)
                Flight.setProp(ret, "_plan_segment_type", "star")
                Flight.setProp(ret, "_plan_segment_name", star.name)
                waypoints = waypoints[:-1] + ret + [waypoints[-1]]  # insert STAR before airport
                self.arr_procs = (rwyarr, star)
                self.meta["arrival"]["procedure"] = (rwyarr.name, star.name)
            else:
                logger.warning(f":plan: arrival airport {arrapt.icao} has no STAR for runway {rwyarr.name}")
        else:  # no star, we are done, we arrive in a straight line
            logger.warning(f":plan: arrival airport {arrapt.icao} has no STAR")

        # APPCH, we found airports with approaches and no STAR
        if arrapt.has_approaches() and rwyarr is not None:
            appch = arrapt.selectApproach(star, rwyarr)  # star won't be used, we can safely pass star=None
            appch = arrapt.procedures.APPCHS["RW34L"]["I34L"]
            if appch is not None:
                logger.debug(f":plan: {arrapt.icao} using APPCH {appch.name}")
                ret = arrapt.procedures.getRoute(appch, self.managedAirport.airport.airspace)
                Flight.setProp(ret, "_plan_segment_type", "appch")
                Flight.setProp(ret, "_plan_segment_name", appch.name)
                if len(waypoints) > 2 and len(ret) > 0 and waypoints[-2].id == ret[0].id:
                    logger.debug(f":plan: duplicate end STAR/begin APPCH {ret[0].id} removed")
                    waypoints = waypoints[:-2] + ret + [waypoints[-1]]  # remove last point of STAR
                else:
                    waypoints = waypoints[:-1] + ret + [waypoints[-1]]  # insert APPCH before airport
                self.arr_procs = (rwyarr, star, appch)
                self.meta["arrival"]["procedure"] = (rwyarr.name, star.name if star is not None else "no STAR", appch.name)
            else:
                logger.warning(f":plan: arrival airport {arrapt.icao} has no APPCH for {rwyarr.name} ")
        else:
            logger.warning(f":plan: arrival airport {arrapt.icao} has no APPCH")


        idx = 0
        for f in waypoints:
            f.setProp(FEATPROP.FLIGHT_PLAN_INDEX.value, idx)
            idx = idx + 1

        self.flightplan_wpts = waypoints
        # printFeatures(self.flightplan_wpts, "plan")
        logger.debug(f":plan: generated {len(self.flightplan_wpts)} points")
        return (True, "Flight::plan: planned")


    def printFlightPlan(self):
        if self.flightplan_wpts is None:
            logger.warning(":printFlightPlan: no flight plan")
            return
        SEP = ","
        rt = ""
        for w in self.flightplan_wpts:
            wi = w.getId()
            wa = wi.split(":")
            if len(wa) == 4:
                wi = wa[1]
            rt = rt + wi + SEP
        return rt.strip(SEP)


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
