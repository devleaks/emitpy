# Everything Flight
import logging
import traceback
import io
from enum import Enum
from datetime import datetime, timedelta, timezone

from tabulate import tabulate

from emitpy.airspace import FlightRoute
from emitpy.airport import Airport
from emitpy.business import Airline
from emitpy.aircraft import Aircraft
from emitpy.constants import PAYLOAD, FLIGHT_PHASE, FEATPROP, FLIGHT_TIME_FORMAT, ARRIVAL, DEPARTURE, RWY_ARRIVAL_SLOT, RWY_DEPARTURE_SLOT
from emitpy.geo.turf import distance
from emitpy.utils import FT
from emitpy.message import Messages, FlightboardMessage, EstimatedTimeMessage

logger = logging.getLogger("Flight")


class FLIGHT_SEGMENT(Enum):
    RWYDEP = "rwydep"
    RWYARR = "rwyarr"
    SID = "sid"
    STAR = "star"
    APPCH = "appch"
    CRUISE = "cruise"


class Flight(Messages):
    def __init__(
        self,
        operator: Airline,
        number: str,
        scheduled: datetime,
        departure: Airport,
        arrival: Airport,
        aircraft: Aircraft,
        linked_flight: "Flight" = None,
        load_factor: float = 1.0,
    ):
        Messages.__init__(self)

        self._movement = None
        self.number = number
        self.departure = departure
        self.arrival = arrival
        self.alternate = None
        self.linked_flight = linked_flight
        self.managedAirport = None
        self.scheduled_dt = scheduled
        self.scheduled = scheduled.isoformat()
        self.estimated_dt = None
        self.estimated = None
        self.actual_dt = None
        self.actual = None
        self.opposite_scheduled_dt = None  # Opposite's airport estimation of STA/STD
        self.opposite_estimated_dt = None  # Opposite's airport ETA/ETD

        self.operator = operator
        self.aircraft = aircraft
        self.ramp = None  # GeoJSON Feature
        self.runway = None  # GeoJSON Feature
        self.tarprofile = None
        self.turnaround = None
        self.codeshare = None
        self.phase = FLIGHT_PHASE.SCHEDULED if scheduled else FLIGHT_PHASE.UNKNOWN
        self.flight_level = 0
        self.flightroute = None  # FlightRoute object
        self.flightplan_wpts = []
        self.procedures = {}
        self.rwy = None  # RWY object

        self.meta = {"departure": {}, "arrival": {}}
        self.flight_type = PAYLOAD.PAX
        self.load_factor = load_factor  # 100% capacity, estimated, both passengers and cargo.

        # try:
        #     if int(number) > 5000:
        #         if int(number) > 9900:
        #             self.flight_type = PAYLOAD.TECH
        #         else:
        #             self.flight_type = PAYLOAD.CARGO
        # except ValueError:
        #     self.flight_type = PAYLOAD.PAX

        self.schedule_opposite()

        if linked_flight is not None and linked_flight.linked_flight is None:
            linked_flight.setLinkedFlight(self)  # will do self.setLinkedFlight(linked_flight)

        self.aircraft.setCallsign(self.operator.icao + self.number)  # default

    @staticmethod
    def setProp(arr: list, propname: str, value: str):
        for a in arr:
            a.setProp(propname, value)

    def __str__(self):
        def airc(ac):
            if ac is None:
                logger.debug("no aircraft")
                return ""
            return ac.actype.typeId + "(" + ac.registration + ")"

        def dproc():
            s = ""
            e = self.procedures.get(FLIGHT_SEGMENT.RWYDEP.value)
            s = e.name if e is not None else "RW--"
            e = self.procedures.get(FLIGHT_SEGMENT.SID.value)
            s = s + " SID " + e.name if e is not None else "-none-"
            return s

        def aproc():
            s = ""
            e = self.procedures.get(FLIGHT_SEGMENT.STAR.value)
            s = s + "STAR " + e.name if e is not None else "-none-"
            e = self.procedures.get(FLIGHT_SEGMENT.APPCH.value)
            s = s + " APPCH " + e.name if e is not None else "-none-"
            e = self.procedures.get(FLIGHT_SEGMENT.RWYARR.value)
            s = s + " " + e.name if e is not None else "RW--"
            return s

        s = self.getName()
        s = s + f" {self.departure.iata}-{self.arrival.iata} {airc(self.aircraft)} FL{self.flight_level}"
        s = s + f" //DEP {self.departure.icao} {dproc()} //ARR {self.arrival.icao} {aproc()}"
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
        scheduled_utc = datetime.strptime(a[1], "S" + FLIGHT_TIME_FORMAT).replace(tzinfo=timezone.utc)
        return (a[0], scheduled_utc, a[0][0:2], a[2:])

    def set_movement(self, move):
        self._movement = move

    def get_movement(self):
        return self._movement

    def getName(self) -> str:
        """
        Gets the name.

        :returns:   The name.
        :rtype:     str
        """
        return self.operator.iata + " " + self.number

    def getDisplayName(self) -> str:
        return self.operator.iata + " " + self.number + " " + self.scheduled_dt.strftime("%H:%M")

    def getEstimatedTime(self):
        return self.estimated_dt

    def is_cargo(self):
        """
        Returns whether a flight is a pure cargo/freit flight.
        """
        return self.flight_type == PAYLOAD.CARGO

    def set_cargo(self):
        """
        Set flight as pure cargo/freit flight.
        """
        self.flight_type = PAYLOAD.CARGO

    def has_jetway(self):
        """
        Returns whether flight is at a stand with a jetway.
        """
        if self.ramp is not None:
            if hasattr(self.ramp, "has_jetway"):
                return self.ramp.has_jetway()
            return self.ramp.getProp(FEATPROP.JETWAY)
        return False

    def getTurnaroundProfile(self, redis=None):
        if self.tarprofile is not None:
            return self.tarprofile
        self.tarprofile = self.managedAirport.airport.manager.getTurnaroundProfile(self, redis)
        return self.tarprofile

    def is_arrival(self) -> bool:
        if self.managedAirport is not None:
            return self.arrival.icao == self.managedAirport.icao
        logger.warning(f"no managedAirport, cannot determine")
        return None

    def is_departure(self) -> bool:
        if self.managedAirport is not None:
            return self.departure.icao == self.managedAirport.icao
        logger.warning(f"no managedAirport, cannot determine")
        return None

    def get_move(self, opposite: bool = False) -> str:
        if self.is_arrival():
            return ARRIVAL if not opposite else DEPARTURE
        return DEPARTURE if not opposite else ARRIVAL

    def estimate_opposite(self, travel_time: int = None):
        # Estimate a gross ETA/ETD given flight distance and aircraft cruise speed.
        # This is an approximation, but gives an idea to get opposite airport weather info.
        # If travel_time is supplied, refines the estimate.
        supplied = True
        dist = self.departure.miles(self.arrival)  # nm
        speed = None  # will be in kn
        actype = self.aircraft.actype
        if actype is not None:
            speed = actype.get("cruise_speed")
        if speed is None:
            speed = 600  # kn
        if travel_time is None:  # estimate it
            supplied = False
            travel_time = 3600 * dist / speed  # seconds

        if self.is_arrival():
            travel_time = -travel_time
        estimated_dt = self.estimated_dt if self.estimated_dt is not None else self.scheduled_dt
        self.opposite_estimated_dt = estimated_dt + timedelta(seconds=travel_time)
        logger.debug(
            f"estimated {self.get_move(opposite=True)} estimated at: {self.opposite_estimated_dt} (distance={round(dist, 0)}nm, travel time={round(- travel_time, 1)} seconds ({'supplied' if supplied else 'estimated'}) at {round(speed, 0)}kn)"
        )

    def schedule_opposite(self, travel_time: int = None):
        # Estimate a gross ETA/ETD given flight distance and aircraft cruise speed.
        # This is an approximation, but gives an idea to get opposite airport weather info.
        # If travel_time is supplied, refines the estimate.
        supplied = True
        dist = self.departure.miles(self.arrival)  # nm
        speed = None  # will be in kn
        actype = self.aircraft.actype
        if actype is not None:
            speed = actype.get("cruise_speed")
        if speed is None:
            speed = 600  # kn
        if travel_time is None:  # estimate it
            supplied = False
            travel_time = 3600 * dist / speed  # hours

        if self.is_arrival():
            travel_time = -travel_time
        self.opposite_scheduled_dt = self.scheduled_dt + timedelta(seconds=travel_time)
        logger.debug(
            f"scheduled {self.get_move(opposite=True)} estimated at: {self.opposite_scheduled_dt} (distance={round(dist, 0)}nm, travel time={round(- travel_time, 1)} seconds ({'supplied' if supplied else 'estimated'}) at {round(speed, 0)}kn)"
        )

    def getScheduledDepartureTime(self):
        return self.scheduled_dt if self.is_departure() else self.opposite_scheduled_dt

    def getScheduledArrivalTime(self):
        return self.scheduled_dt if self.is_arrival() else self.opposite_scheduled_dt

    def get_oooi(self, gate: bool = False) -> str:
        # Returns the flight phase name corresponding to the movement
        # ACARS OOOI (Out of the gate, Off the ground, On the ground, and Into the gate)
        if gate:
            if self.is_arrival():
                return FLIGHT_PHASE.ONBLOCK.value
            return FLIGHT_PHASE.OFFBLOCK.value

        if self.is_arrival():
            return FLIGHT_PHASE.TOUCH_DOWN.value
        return FLIGHT_PHASE.TAKE_OFF.value

    def getRemoteAirport(self) -> Airport:
        return self.departure if self.is_arrival() else self.arrival

    def setLinkedFlight(self, linked_flight: "Flight") -> None:
        # Should check if already defined and different
        if linked_flight.linked_flight is None:
            self.linked_flight = linked_flight
            linked_flight.linked_flight = self
            logger.debug(f"{self.getId()} linked to {linked_flight.getId()}")
        else:
            logger.warning(f"{linked_flight.getId()} already linked")

    def setFL(self, flight_level: int) -> None:
        self.flight_level = flight_level
        if flight_level <= 100:
            logger.warning(f"{self.flight_level}")
        else:
            logger.debug(f"{self.flight_level}")

    def setLoadFactor(self, load_factor: float):
        if load_factor >= 0 and load_factor <= 2:
            self.load_factor = load_factor
        else:
            logger.warning(f"invalid load factor {load_factor} ∉ [0,2]")

    def setFlightService(self, flight_service: "FlightService"):
        self.turnaround = flight_service

    def setTurnaround(self, turnaround: "Turnaround"):
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
            reqend = reqtime + timedelta(minutes=120)
            if am.ramp_allocator.isAvailable(name, reqtime, reqend):
                res = am.ramp_allocator.book(name, reqtime, reqend, self.getId())
            self.ramp = ramp
            logger.debug(f"flight {self.getName()}: ramp {name}")
        else:
            logger.warning(f"{name} not found, ramp unchanged")

    def setGate(self, gate):
        """
        For information only. Not used.

        :param      gate:  The gate
        :type       gate:  { type_description }
        """
        self.gate = gate
        logger.debug(f"flight {self.getName()}: gate {self.gate}")

    def setRWY(self, rwy):
        self.rwy = rwy
        self._setRunway()
        logger.debug(f"{self.getName()}: {self.rwy.name}")

    def _setRunway(self, move):
        if self.rwy is not None:
            if move is not None:
                self.runway = move.getRunway(self.rwy)
                if self.runway is not None:
                    name = self.runway.getResourceId()
                    # if name[0:2] != "RW":  # add it
                    #     logger.debug(f"correcting: RW+{name}")
                    #     name = "RW" + name
                    am = self.managedAirport.airport.manager
                    if name in am.runway_allocator.resources.keys():
                        reqtime = self.scheduled_dt + timedelta(minutes=20)  # time to taxi
                        reqduration = RWY_DEPARTURE_SLOT if self.is_departure() else RWY_ARRIVAL_SLOT
                        reqend = reqtime + timedelta(seconds=reqduration)  # time to take-off + WTC spacing
                        #
                        # @TODO: If not available, should take next availability and "queue"
                        #
                        if am.runway_allocator.isAvailable(name, reqtime, reqend):
                            res = am.runway_allocator.book(name, reqtime, reqend, self.getId())
                        logger.debug(f"flight {self.getName()}: runway {name} ({self.rwy.name})")
                    else:
                        logger.warning(f"resource {name} not found, runway unchanged")
                    logger.debug(f"{self.getName()}: {name}")
                else:
                    logger.warning("no runway, runway unchanged")
            else:
                logger.warning("no move, runway unchanged")
        else:
            logger.warning("no RWY, runway unchanged")

    def makeFlightRoute(self):
        self.flightroute = FlightRoute(managedAirport=self.managedAirport, fromICAO=self.departure.icao, toICAO=self.arrival.icao)

        if not self.flightroute.has_route():
            logger.warning("no flight route on airways")
            self.flightroute.makeGreatCircleFlightRoute()
            if not self.flightroute.has_route():
                logger.warning("no flight route, cannot proceed.")
                return

        fplen = len(self.flightroute.nodes())
        if fplen < 4:  # 4 features means 3 nodes (dept, fix, arr) and LineString.
            logger.warning(f"flight route is too short {fplen}")
        logger.debug(f"loaded {fplen} waypoints")

    def printFlightRoute(self):
        if self.flightroute is None or not self.flightroute.has_route():
            logger.warning("no flight route")
            return
        return self.flightroute.print()

    def tabulateFlightRoute(self):
        if self.flightroute is None or not self.flightroute.has_route():
            logger.warning("no flight route")
            return

        output = io.StringIO()
        print("\nFLIGHT ROUTE", file=output)
        HEADER = ["INDEX", "WAYPOINT", "NODE"]
        table = []

        a = self.flightroute.getAirspace()
        idx = 0
        for n in self.flightroute.nodes():
            f = a.get_vertex(n)
            table.append([idx, f.ident, f.getId()])
            idx = idx + 1

        table = sorted(table, key=lambda x: x[0])  # absolute emission time
        print(tabulate(table, headers=HEADER), file=output)
        contents = output.getvalue()
        output.close()
        logger.debug(f"{contents}")

    def setEstimatedTime(self, dt: datetime, info_time: datetime = datetime.now().astimezone()):
        self.estimated_dt = dt
        self.estimated = dt.isoformat()
        self.schedule_history.append((dt.isoformat(), "ET", info_time.isoformat()))
        self.estimate_opposite()

        if dt < info_time:
            logger.warning("announce event after occurance")
        rt = dt - info_time
        self.addMessage(EstimatedTimeMessage(flight_id=self.getId(), is_arrival=self.is_arrival(), relative_time=rt.seconds, et=dt))

    def setActualTime(self, dt: datetime, info_time: datetime = datetime.now().astimezone()):
        self.actual_dt = dt
        self.actual = dt.isoformat()
        self.schedule_history.append((dt.isoformat(), "AT", info_time.isoformat()))

    def plan(self):
        if self.flightroute is None:  # not loaded, trying to load
            self.makeFlightRoute()

        if not self.flightroute.has_route():  # not found... stops
            logger.warning("no flight route")
            return (False, "Flight::plan: no flight route")

        normplan = self.flightroute.route()
        waypoints = []

        sync = self.get_oooi(gate=True)

        # Flightboard message sent one hour (3600 secs) before actual scheduled time.
        FLIGHTBOARD_INFO_TIME = -3600  # could be params or constant
        self.addMessage(FlightboardMessage(flight=self, relative_time=FLIGHTBOARD_INFO_TIME, relative_sync=sync))

        # ###########################
        # DEPARTURE AND CRUISE
        #
        depapt = self.departure
        rwydep = None

        # RWY
        # self.meta["departure"]["metar"] = depapt.getMetar()
        if depapt.has_rwys():
            rwydep = depapt.selectRWY(self)
            logger.debug(f"departure airport {depapt.icao} using runway {rwydep.name}")
            if self.is_departure():
                self.setRWY(rwydep)
            waypoints = rwydep.getRoute()
            waypoints[0].setProp(FEATPROP.PLAN_SEGMENT_TYPE, "origin/rwy")
            waypoints[0].setProp(FEATPROP.PLAN_SEGMENT_NAME, depapt.icao + "/" + rwydep.name)
            self.procedures[FLIGHT_SEGMENT.RWYDEP.value] = rwydep
            self.meta["departure"]["procedure"] = rwydep.name
        else:  # no runway, we leave from airport
            logger.warning(f"departure airport {depapt.icao} has no runway, first point is departure airport")
            dep = depapt.copy()  # depapt.getTerminal().copy() would be more correct
            dep.setProp(FEATPROP.PLAN_SEGMENT_TYPE, "origin")
            dep.setProp(FEATPROP.PLAN_SEGMENT_NAME, depapt.icao)
            waypoints.append(dep)

        # SID
        if depapt.has_sids() and rwydep is not None:
            logger.debug(f"using procedures for departure airport {depapt.icao}")
            sid = depapt.selectSID(rwydep)
            if sid is not None:  # inserts it
                logger.debug(f"{depapt.icao} using SID {sid.name}")
                ret = depapt.procedures.getRoute(sid, self.managedAirport.airport.airspace)
                Flight.setProp(ret, FEATPROP.PLAN_SEGMENT_TYPE.value, FLIGHT_SEGMENT.SID.value)
                Flight.setProp(ret, FEATPROP.PLAN_SEGMENT_NAME.value, sid.name)
                waypoints = waypoints + ret
                self.procedures[FLIGHT_SEGMENT.SID.value] = sid
                self.meta["departure"]["procedure"] = (rwydep.name, sid.name)
            else:
                logger.warning(f"departure airport {depapt.icao} has no SID for {rwydep.name}")

            normplan = normplan[1:]
            Flight.setProp(normplan, FEATPROP.PLAN_SEGMENT_TYPE.value, "cruise")
            Flight.setProp(normplan, FEATPROP.PLAN_SEGMENT_NAME.value, depapt.icao + "-" + self.arrival.icao)
            waypoints = waypoints + normplan

        else:  # no sid, we go straight
            logger.debug(f"departure airport {depapt.icao} has no procedure, flying straight")
            ret = normplan[1:]  # remove departure airport and leave cruise
            Flight.setProp(ret, FEATPROP.PLAN_SEGMENT_TYPE.value, "cruise")
            Flight.setProp(ret, FEATPROP.PLAN_SEGMENT_NAME.value, depapt.icao + "-" + self.arrival.icao)
            waypoints = waypoints + ret

        # ###########################
        # ARRIVAL
        #
        arrapt = self.arrival
        rwyarr = None

        # RWY
        # self.meta["arrival"]["metar"] = depapt.getMetar()
        if arrapt.has_rwys():
            rwyarr = arrapt.selectRWY(self)
            logger.debug(f"arrival airport {arrapt.icao} using runway {rwyarr.name}")
            if self.is_arrival():
                self.setRWY(rwyarr)
            ret = rwyarr.getRoute()
            Flight.setProp(ret, FEATPROP.PLAN_SEGMENT_TYPE.value, "destination/rwy")
            Flight.setProp(ret, FEATPROP.PLAN_SEGMENT_NAME.value, rwyarr.name)
            waypoints = waypoints[:-1] + ret  # no need to add last point which is arrival airport, we replace it with the precise runway end.
            self.procedures[FLIGHT_SEGMENT.RWYARR.value] = rwyarr
            self.meta["arrival"]["procedure"] = rwyarr.name
        else:  # no star, we are done, we arrive in a straight line
            logger.warning(f"arrival airport {arrapt.icao} has no runway, last point is arrival airport")
            waypoints.append(arrapt)  # and rwyarr is None

        # STAR
        star = None  # used in APPCH
        star_route = None
        if arrapt.has_stars() and rwyarr is not None:
            star = arrapt.selectSTAR(rwyarr)
            if star is not None:
                logger.debug(f"{arrapt.icao} using STAR {star.name}")
                ret = arrapt.procedures.getRoute(star, self.managedAirport.airport.airspace)
                Flight.setProp(ret, FEATPROP.PLAN_SEGMENT_TYPE.value, FLIGHT_SEGMENT.STAR.value)
                Flight.setProp(ret, FEATPROP.PLAN_SEGMENT_NAME.value, star.name)
                waypoints = waypoints[:-1] + ret + [waypoints[-1]]  # insert STAR before airport
                self.procedures[FLIGHT_SEGMENT.STAR.value] = star
                self.meta["arrival"]["procedure"] = (rwyarr.name, star.name)
                star_route = ret
            else:
                logger.warning(f"arrival airport {arrapt.icao} has no STAR for runway {rwyarr.name}")
        else:  # no star, we are done, we arrive in a straight line
            logger.warning(f"arrival airport {arrapt.icao} has no STAR")

        # APPCH, we found airports with approaches and no STAR
        if arrapt.has_approaches() and rwyarr is not None:
            appch = arrapt.selectApproach(star, rwyarr)  # star won't be used, we can safely pass star=None
            if appch is not None:
                logger.debug(f"{arrapt.icao} using APPCH {appch.name}")
                ret = arrapt.procedures.getRoute(appch, self.managedAirport.airport.airspace)
                Flight.setProp(ret, FEATPROP.PLAN_SEGMENT_TYPE.value, FLIGHT_SEGMENT.APPCH.value)
                Flight.setProp(ret, FEATPROP.PLAN_SEGMENT_NAME.value, appch.name)
                if len(waypoints) > 2 and len(ret) > 0 and waypoints[-2].id == ret[0].id:
                    logger.debug(f"duplicate end STAR/begin APPCH {ret[0].id} removed")
                    waypoints = waypoints[:-2] + ret + [waypoints[-1]]  # remove last point of STAR
                else:
                    waypoints = waypoints[:-1] + ret + [waypoints[-1]]  # insert APPCH before airport
                self.procedures[FLIGHT_SEGMENT.APPCH.value] = appch
                self.meta["arrival"]["procedure"] = (rwyarr.name, star.name if star is not None else "no STAR", appch.name)
            else:
                logger.warning(f"arrival airport {arrapt.icao} has no APPCH for {rwyarr.name} ")
        else:
            logger.warning(f"arrival airport {arrapt.icao} has no APPCH")

        idx = 0
        for f in waypoints:
            # logger.debug(f"flight plan: {f.getProp('_plan_segment_type')} {f.getProp('_plan_segment_name')}, {type(f).__name__}")
            f.setProp(FEATPROP.FLIGHT_PLAN_INDEX, idx)
            if hasattr(f, "hasRestriction") and f.hasRestriction():
                f.setProp(FEATPROP.RESTRICTION, f.getRestrictionDesc())
            idx = idx + 1

        self.flightplan_wpts = waypoints
        # printFeatures(self.flightplan_wpts, "plan")
        logger.debug(f"generated {len(self.flightplan_wpts)} points")
        return (True, "Flight::plan: planned")

    def printFlightPlan(self):
        if self.flightplan_wpts is None:
            logger.warning("no flight plan")
            return
        SEP = ","
        rt = []
        for w in self.flightplan_wpts:
            wi = w.ident
            if hasattr(w, "hasRestriction") and w.hasRestriction():
                wi = f"{w.ident} ({w.getRestrictionDesc()})"
            rt.append(wi)
        return SEP.join(rt)

    def tabulateFlightPlan(self):
        if self.flightplan_wpts is None:
            logger.warning("no flight plan")
            return

        output = io.StringIO()
        print("\nFLIGHT PLAN", file=output)
        HEADER = [
            "INDEX",
            "SEGMENT TYPE",
            "SEGMENT NAME",
            "WAYPOINT",
            "NODE",
            "RESTRICTIONS",
            "DISTANCE",
            "TOTAL DISTANCE",
            "MIN ALT",
            "MAX ALT",
            "ALT TARGET",
            "MIN SPEED",
            "MAX SPEED",
            "SPEED TARGET",
        ]
        table = []

        total_dist = 0
        last_point = None
        for w in self.flightplan_wpts:
            d = 0
            if last_point is not None:
                d = distance(last_point, w)
                total_dist = total_dist + d

            table.append(
                [
                    w.getProp(FEATPROP.FLIGHT_PLAN_INDEX),
                    w.getProp(FEATPROP.PLAN_SEGMENT_TYPE),
                    w.getProp(FEATPROP.PLAN_SEGMENT_NAME),
                    w.getId(),
                    w.ident if hasattr(w, "ident") else "no ident",
                    w.getRestrictionDesc() if hasattr(w, "hasRestriction") and w.hasRestriction() else "",
                    round(d, 1),
                    round(total_dist),
                    w.getProp("_alt_min"),
                    w.getProp("_alt_max"),
                    w.getProp("_alt_target"),
                    w.getProp("_speed_min"),
                    w.getProp("_speed_max"),
                    w.getProp("_speed_target"),
                ]
            )
            last_point = w

        table = sorted(table, key=lambda x: x[0])  # absolute emission time
        print(tabulate(table, headers=HEADER), file=output)
        contents = output.getvalue()
        output.close()
        return contents

    def distance(self, idx_start, idx_end):
        """Returns total distance between waypoints following flight path"""
        last_point = self.flightplan_wpts[idx_start]
        idx = idx_start + 1
        total_dist = 0.0
        while idx <= idx_end and idx < len(self.flightplan_wpts):
            w = self.flightplan_wpts[idx]
            d = distance(last_point, w)
            total_dist = total_dist + d
            idx = idx + 1
        return total_dist

    def next_restriction(self, idx_start, backwards: bool = False, fun: str = "hasRestriction"):
        """Returns waypoint with restriction following supplied index.
        Also returns distance to that waypoint, i.e. distance to comply with the next restriction
        """
        if fun not in ["hasRestriction", "hasSpeedRestriction", "hasAltitudeRestriction"]:
            logger.warning(f"invalid test function {fun}")
            return None

        last_point = self.flightplan_wpts[idx_start]
        total_dist = 0.0

        if backwards:
            idx = idx_start - 1
            while idx >= 0:
                w = self.flightplan_wpts[idx]
                d = distance(last_point, w)
                total_dist = total_dist + d
                if hasattr(w, fun):
                    func = getattr(w, fun)
                    if func():
                        return w  # (w, d)
                idx = idx - 1
                last_point = w
        else:
            idx = idx_start + 1
            while idx < len(self.flightplan_wpts):
                w = self.flightplan_wpts[idx]
                d = distance(last_point, w)
                total_dist = total_dist + d
                if hasattr(w, fun):
                    func = getattr(w, fun)
                    if func():
                        return w  # (w, d)
                idx = idx + 1
                last_point = w
        return None


class Arrival(Flight):
    def __init__(
        self,
        number: str,
        scheduled: datetime,
        managedAirport: Airport,
        origin: Airport,
        operator: Airline,
        aircraft: Aircraft,
        load_factor: float = 1.0,
        linked_flight: "Flight" = None,
    ):
        Flight.__init__(
            self,
            number=number,
            scheduled=scheduled,
            departure=origin,
            arrival=managedAirport.airport,
            operator=operator,
            aircraft=aircraft,
            load_factor=load_factor,
            linked_flight=linked_flight,
        )
        self.managedAirport = managedAirport

    def _setRunway(self):
        super()._setRunway(self.arrival)

    def is_arrival(self) -> bool:
        return True

    def is_departure(self) -> bool:
        return False


class Departure(Flight):
    def __init__(
        self,
        number: str,
        scheduled: datetime,
        managedAirport: Airport,
        destination: Airport,
        operator: Airline,
        aircraft: Aircraft,
        load_factor: float = 1.0,
        linked_flight: "Flight" = None,
    ):
        Flight.__init__(
            self,
            number=number,
            scheduled=scheduled,
            departure=managedAirport.airport,
            arrival=destination,
            operator=operator,
            aircraft=aircraft,
            load_factor=load_factor,
            linked_flight=linked_flight,
        )
        self.managedAirport = managedAirport

    def _setRunway(self):
        super()._setRunway(self.departure)

    def is_arrival(self) -> bool:
        return False

    def is_departure(self) -> bool:
        return True
