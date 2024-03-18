# Everything Flight
import logging
import re
import traceback
import io
import os
import json
from typing import Tuple
from enum import Enum
from datetime import datetime, timedelta, timezone

from tabulate import tabulate

from emitpy.parameters import MANAGED_AIRPORT_AODB
from emitpy.constants import PAYLOAD, FLIGHT_PHASE, FLIGHT_TIME_FORMAT, ARRIVAL, DEPARTURE, RWY_ARRIVAL_SLOT, RWY_DEPARTURE_SLOT, FLIGHT_SEGMENT
from emitpy.constants import FLIGHT_DATABASE, FEATPROP
from emitpy.airspace import FlightRoute
from emitpy.airport import Airport
from emitpy.airspace.restriction import FeatureWithRestriction
from emitpy.business import Airline
from emitpy.aircraft import Aircraft
from emitpy.geo.turf import distance
from emitpy.utils import convert
from emitpy.message import Messages, FlightboardMessage, EstimatedTimeMessage
from emitpy.utils.interpolate import compute_time

logger = logging.getLogger("Flight")


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
        self.cruise_speed = 0.85  # mach
        self.flightroute = None  # FlightRoute object
        self.flightplan_wpts = []

        # New feature!
        self.runway_slot = -1
        self.runway_slot_dt = None

        self.procedures = {}
        self.rwy = None  # RWY object

        self.meta = {"departure": {}, "arrival": {}}
        self.flight_type = PAYLOAD.PAX
        self.load_factor = load_factor  # 100% capacity, estimated, both passengers and cargo.

        self.forced_procedures = None
        self.comment: str = ""
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
            s = s + (" SID " + e.name if e is not None else "-none-")
            return s

        def aproc():
            s = ""
            e = self.procedures.get(FLIGHT_SEGMENT.STAR.value)
            s = s + "STAR " + (e.name if e is not None else "-none-")
            e = self.procedures.get(FLIGHT_SEGMENT.APPCH.value)
            s = s + " APPCH " + (e.name if e is not None else "-none-")
            e = self.procedures.get(FLIGHT_SEGMENT.RWYARR.value)
            s = s + " " + (e.name if e is not None else "RW--")
            return s

        s = self.getName()
        s = s + f" {self.departure.iata}-{self.arrival.iata} {airc(self.aircraft)} FL{self.flight_level}"
        s = s + f" //DEP {self.departure.icao} {dproc()} //ARR {self.arrival.icao} {aproc()}"
        if self.comment is not None:
            s = s + f"(note: {self.comment})"
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
            "runway": (self.runway.getInfo() if self.runway is not None else {}),  # note: this is the GeoJSON feature, not the RWY procedure
            "is_arrival": self.is_arrival(),  # simply useful denormalisation...
            "comment": self.comment,
            "summary": str(self),
            "procedures": self.force_string()
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

    def saveFile(self, **kwargs):
        if kwargs.get("info"):
            basename = os.path.join(MANAGED_AIRPORT_AODB, FLIGHT_DATABASE, self.getId())
            filename = basename + "-0-info.json"
            with open(filename, "w") as fp:
                json.dump(self.getInfo(), fp, indent=4)

        logger.debug(f"saved {self.getId()}")
        return (True, "Flight::saveFile saved")

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

    def setCruise(self, flight_level: int, cruise_speed: float = 0.85) -> None:
        self.flight_level = flight_level
        if flight_level <= 100:
            logger.warning(f"{self.flight_level}")
        else:
            logger.debug(f"{self.flight_level}")
        self.cruise_speed = cruise_speed

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
        return convert.feet_to_meters(self.flight_level * 100)

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

    def makeFlightRoute(self) -> bool:
        self.flightroute = FlightRoute(managedAirport=self.managedAirport, fromICAO=self.departure.icao, toICAO=self.arrival.icao)

        if not self.flightroute.has_route():
            logger.warning("no flight route on airways")
            self.flightroute.makeGreatCircleFlightRoute()
            if not self.flightroute.has_route():
                logger.warning("no flight route, cannot proceed.")
                return False

        fplen = len(self.flightroute.nodes())
        if fplen < 4:  # 4 features means 3 nodes (dep, fix, arr) and LineString.
            logger.warning(f"flight route is too short {fplen}")
            # return False
        logger.debug(f"loaded {fplen} waypoints")
        return True

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

    def force_procedures(self, rwydep, sid, star, appch, rwyarr, **kwargs):
        """For debugging purpose to set reproducible situations"""
        logger.info(f"forcing procedures departure={rwydep}, sid={sid}, star={star}, approach={appch}, arrival={rwyarr}")
        depapt = self.departure
        arrapt = self.arrival
        deprwy = depapt.procedures.RWYS.get(rwydep)
        arrrwy = arrapt.procedures.RWYS.get(rwyarr)
        self.forced_procedures = {
            FLIGHT_SEGMENT.RWYDEP.value: deprwy,
            FLIGHT_SEGMENT.SID.value: depapt.procedures.BYNAME.get(sid),
            FLIGHT_SEGMENT.STAR.value: arrapt.procedures.BYNAME.get(star),
            FLIGHT_SEGMENT.APPCH.value: arrapt.procedures.BYNAME.get(appch),
            FLIGHT_SEGMENT.RWYARR.value: arrrwy,
        }
        # logger.debug(f"forced procedures {self.forced_procedures}")

    def force_string(self):
        def nvl(a):
            b = self.procedures.get(a.value)
            return f"'{b.name}'" if b is not None else None

        if self.procedures is None:
            return "{}"

        return "{" + ", ".join([f"'{i.value}': {nvl(i)}" for i in FLIGHT_SEGMENT]) + "}"

    # [
    #                 f"{{'{FLIGHT_SEGMENT.RWYDEP.value}': {nvl(FLIGHT_SEGMENT.RWYDEP)}",
    #                 f"'sid': {nvl(FLIGHT_SEGMENT.SID)}",
    #                 f"'star': {nvl(FLIGHT_SEGMENT.STAR)}",
    #                 f"'appch': {nvl(FLIGHT_SEGMENT.APPCH)}",
    #                 f"'rwyarr': {nvl(FLIGHT_SEGMENT.RWYARR)}}}",

    def has_imposed_procedures(self) -> bool:
        return self.forced_procedures is not None and len(self.forced_procedures) > 1

    def plan_get_rwydep(self):
        if self.has_imposed_procedures():
            return self.forced_procedures.get(FLIGHT_SEGMENT.RWYDEP.value)
        rwy = self.procedures.get(FLIGHT_SEGMENT.RWYDEP.value)
        if rwy is not None:
            return rwy
        if self.departure.has_rwys():
            rwy = self.departure.selectRWY(self)
            if rwy is not None:
                return rwy
        logger.debug(f"departure airport {self.departure.icao} no runway found")
        return None

    def plan_get_sid(self, rwydep):
        if self.has_imposed_procedures():
            return self.forced_procedures.get(FLIGHT_SEGMENT.SID.value)
        sid = self.procedures.get(FLIGHT_SEGMENT.SID.value)
        if sid is not None:
            return sid
        if self.departure.has_sids():
            sid = self.departure.selectSID(rwydep, self.arrival, self.managedAirport.airport.airspace)
            if sid is not None:
                return sid
        logger.debug(f"departure airport {self.departure.icao} no SID found")
        return None

    def plan_get_rwyarr(self):
        if self.has_imposed_procedures():
            return self.forced_procedures.get(FLIGHT_SEGMENT.RWYARR.value)
        rwy = self.procedures.get(FLIGHT_SEGMENT.RWYARR.value)
        if rwy is not None:
            return rwy
        if self.arrival.has_rwys():
            rwy = self.arrival.selectRWY(self)
            if rwy is not None:
                return rwy
        logger.debug(f"arrival airport {self.arrival.icao} no runway found")
        return None

    def plan_get_star(self, rwyarr):
        if self.has_imposed_procedures():
            return self.forced_procedures.get(FLIGHT_SEGMENT.STAR.value)
        star = self.procedures.get(FLIGHT_SEGMENT.STAR.value)
        if star is not None:
            return star
        if self.arrival.has_stars():
            star = self.arrival.selectSTAR(rwyarr, self.departure, self.managedAirport.airport.airspace)
            if star is not None:
                return star
        logger.debug(f"arrival airport {self.arrival.icao} no STAR found")
        return None

    def plan_get_appch(self, star, rwyarr):
        if self.has_imposed_procedures():
            return self.forced_procedures.get(FLIGHT_SEGMENT.APPCH.value)
        appch = self.procedures.get(FLIGHT_SEGMENT.APPCH.value)
        if appch is not None:
            return appch
        if self.arrival.has_approaches():
            appch = self.arrival.selectApproach(star, rwyarr)
            if appch is not None:
                return appch
        logger.debug(f"arrival airport {self.arrival.icao} no APPCH found")
        return None

    def plan(self):
        if self.flightroute is None:  # not loaded, trying to load
            if not self.makeFlightRoute():
                logger.warning("no flight route")
                return (False, "Flight::plan: no flight route")

        if not self.flightroute.has_route():  # not found... stops
            logger.warning("no flight route")
            return (False, "Flight::plan: no flight route")

        route = self.flightroute.route()
        logger.debug(f"route has {len(route)} points")
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
        forced = " (FORCED)" if self.has_imposed_procedures() else ""
        if depapt.has_rwys():
            rwydep = self.plan_get_rwydep()
            if rwydep is not None:
                logger.debug(f"departure airport {depapt.icao} using runway {rwydep.name}{forced}")
                if self.is_departure():
                    self.setRWY(rwydep)
                waypoints = rwydep.getRoute()
                waypoints[0].setProp(FEATPROP.PLAN_SEGMENT_TYPE, "origin/rwy")
                waypoints[0].setProp(FEATPROP.PLAN_SEGMENT_NAME, depapt.icao + "/" + rwydep.name)
                self.procedures[FLIGHT_SEGMENT.RWYDEP.value] = rwydep
                self.meta["departure"]["procedure"] = rwydep.name
            else:
                logger.debug(f"departure airport {depapt.icao} no runway found")
        else:  # no runway, we leave from airport
            logger.warning(f"departure airport {depapt.icao} has no runway, first point is departure airport")
            dep = depapt.copy()  # depapt.getTerminal().copy() would be more correct
            dep.setProp(FEATPROP.PLAN_SEGMENT_TYPE, "origin")
            dep.setProp(FEATPROP.PLAN_SEGMENT_NAME, depapt.icao)
            waypoints.append(dep)

        # SID
        if depapt.has_sids() and rwydep is not None:
            logger.debug(f"using procedures for departure airport {depapt.icao}")
            sid = self.plan_get_sid(rwydep=rwydep)
            if sid is not None:  # inserts it
                logger.debug(f"{depapt.icao} using SID {sid.name}{forced}")
                ret = depapt.procedures.getRoute(sid, self.managedAirport.airport.airspace)
                Flight.setProp(ret, FEATPROP.PLAN_SEGMENT_TYPE.value, FLIGHT_SEGMENT.SID.value)
                Flight.setProp(ret, FEATPROP.PLAN_SEGMENT_NAME.value, sid.name)
                waypoints = waypoints + ret
                self.procedures[FLIGHT_SEGMENT.SID.value] = sid
                self.meta["departure"]["procedure"] = (rwydep.name, sid.name)
            else:
                logger.warning(f"departure airport {depapt.icao} has no SID for {rwydep.name}")

        else:  # no sid, we go straight
            logger.debug(f"departure airport {depapt.icao} has no procedure, flying straight")

        # adding cruise route
        #
        # should may be remove more than first point?
        # remove cruise points until they are after end of SID
        #
        if len(waypoints) > 1:  # if SID added
            departure_airport = waypoints[0]  # departure airport
            end_of_sid = waypoints[-1]
            sidenddist = distance(departure_airport, end_of_sid)
            logger.debug(f"SID ends at {round(sidenddist)}km")
            end = 1
            while distance(departure_airport, route[end]) < sidenddist and end < len(route):
                logger.debug(f"removed cruise point {end} because closer than SID end ({round(distance(departure_airport, route[end]))}km)")
                end = end + 1
            route = route[end:]
            logger.debug(f"keep route from {end} on")

            cruisestart = distance(departure_airport, route[0])
            logger.debug(f"cruise starts at {round(cruisestart)}km")
            d2 = distance(end_of_sid, route[0])
            logger.debug(f"cruise starts {round(d2, 3)}km after end if SID")
            if d2 < 1:  # probably last point of SID and first point of CRUISE are same point
                logger.debug(f"removing first cruise point (probably same point)")
                route = route[1:]
                d2 = distance(end_of_sid, route[0])
                logger.debug(f"cruise now starts {round(d2, 3)}km after end if SID")
        else:  # probably no SID
            logger.debug(f"no SID, route starts after departure airport")
            route = route[1:]

        Flight.setProp(route, FEATPROP.PLAN_SEGMENT_TYPE.value, FLIGHT_SEGMENT.CRUISE.value)
        Flight.setProp(route, FEATPROP.PLAN_SEGMENT_NAME.value, depapt.icao + "-" + self.arrival.icao)
        waypoints = waypoints + route
        logger.debug(f"route added ({len(route)} pts)")

        # ###########################
        # ARRIVAL
        #
        arrapt = self.arrival
        rwyarr = None
        # RWY
        # self.meta["arrival"]["metar"] = depapt.getMetar()
        if arrapt.has_rwys():
            rwyarr = self.plan_get_rwyarr()
            if rwyarr is not None:
                logger.debug(f"arrival airport {arrapt.icao} using runway {rwyarr.name}{forced}")
                if self.is_arrival():
                    self.setRWY(rwyarr)
                ret = rwyarr.getRoute()  # route for airport is 1 point only, the airport (len=1)
                Flight.setProp(ret, FEATPROP.PLAN_SEGMENT_TYPE.value, FLIGHT_SEGMENT.RWYARR.value)
                Flight.setProp(ret, FEATPROP.PLAN_SEGMENT_NAME.value, rwyarr.name)
                waypoints = waypoints[:-1] + ret  # no need to add last point which is arrival airport, we replace it with the precise runway end.
                self.procedures[FLIGHT_SEGMENT.RWYARR.value] = rwyarr
                self.meta["arrival"]["procedure"] = rwyarr.name
            else:
                logger.debug(f"arrival airport {arrapt.icao} no runway found")
        else:  # no star, we are done, we arrive in a straight line
            logger.warning(f"arrival airport {arrapt.icao} has no runway, last point is arrival airport")
            waypoints.append(arrapt)  # and rwyarr is None

        arrival_airport = waypoints[-1]  # arrival airport
        # STAR
        star = None  # used in APPCH
        star_route = None
        if arrapt.has_stars() and rwyarr is not None:
            star = self.plan_get_star(rwyarr=rwyarr)
            if star is not None:
                logger.debug(f"{arrapt.icao} using STAR {star.name}{forced}")
                ret = arrapt.procedures.getRoute(star, self.managedAirport.airport.airspace)
                Flight.setProp(ret, FEATPROP.PLAN_SEGMENT_TYPE.value, FLIGHT_SEGMENT.STAR.value)
                Flight.setProp(ret, FEATPROP.PLAN_SEGMENT_NAME.value, star.name)
                #
                # should may be remove more than last point?
                #
                starstart = distance(ret[0], arrival_airport)
                logger.debug(f"STAR begins at {round(starstart)}km, {len(waypoints)} waypoints total")
                end = len(waypoints) - 1
                while distance(waypoints[end], arrival_airport) < starstart and end > 0:
                    logger.debug(f"removed cruise point {end} because closer than STAR ({round(distance(waypoints[end], waypoints[-1]))}km)")
                    end = end - 1
                logger.debug(f"keep point from {end}/{len(waypoints)} pts")
                waypoints = waypoints[: end + 1]
                waypoints.append(arrival_airport)
                logger.debug(f"last cruise point at ({round(distance(waypoints[-2], waypoints[-1]))}km), {len(waypoints)} left")
                waypoints = waypoints[:-1] + ret + [waypoints[-1]]  # insert STAR before airport, which is last point only (len=1)
                self.procedures[FLIGHT_SEGMENT.STAR.value] = star
                self.meta["arrival"]["procedure"] = (rwyarr.name, star.name)
                star_route = ret
            else:
                logger.warning(f"arrival airport {arrapt.icao} has no STAR for runway {rwyarr.name}")
        else:  # no star, we are done, we arrive in a straight line
            logger.warning(f"arrival airport {arrapt.icao} has no STAR")

        # APPCH, we found airports with approaches and no STAR
        if arrapt.has_approaches() and rwyarr is not None:
            appch = self.plan_get_appch(star=star, rwyarr=rwyarr)
            if appch is not None:
                logger.debug(f"{arrapt.icao} using APPCH {appch.name}{forced}")
                ret = arrapt.procedures.getRoute(appch, self.managedAirport.airport.airspace)
                Flight.setProp(ret, FEATPROP.PLAN_SEGMENT_TYPE.value, FLIGHT_SEGMENT.APPCH.value)
                Flight.setProp(ret, FEATPROP.PLAN_SEGMENT_NAME.value, appch.name)
                if len(waypoints) > 2 and len(ret) > 0 and waypoints[-2].id == ret[0].id:
                    logger.debug(f"duplicate end STAR/begin APPCH {ret[0].id} removed")
                    waypoints = waypoints[:-2] + ret + [waypoints[-1]]  # remove last point of STAR
                else:
                    waypoints = waypoints[:-1] + ret + [waypoints[-1]]  # insert APPCH before airport, which is last point only (len=1)
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
        #
        # Flight plan has no speed...
        #
        # ret = self.time_flight_plan()
        # if not ret[0]:
        #     logger.warning(ret[1])
        # else:
        #     logger.debug(ret[1])
        logger.debug(f"generated {len(self.flightplan_wpts)} points")
        return (True, "Flight::plan: planned")

    def time_flight_plan(self):
        # Flight plan has no speed...
        compute_time(self.flightplan_wpts, self.scheduled_dt.timestamp())
        # tranfer "time" to "flight plan time"
        for f in self.flightplan_wpts:
            f.setProp(FEATPROP.FLIGHT_PLAN_TIME, f.time())
            f.delProp(FEATPROP.TIME)
        logger.debug(f"timed {len(self.flightplan_wpts)} points")
        return (True, "Flight::time_flight_plan: timed")

    def phase_indices(self, phase: FLIGHT_SEGMENT) -> Tuple[int, int | None]:
        """Returns flight plan indices for begin and end of phase"""
        start = None
        # should sort waypoints?
        # fpwpts = sorted(self.flightplan_wpts, key: lambda f: f.getProp(FEATPROP.FLIGHT_PLAN_INDEX))
        for f in self.flightplan_wpts:
            if start is None and f.getProp(FEATPROP.PLAN_SEGMENT_TYPE) == phase.value:
                start = f.getProp(FEATPROP.FLIGHT_PLAN_INDEX)
            if start is not None and f.getProp(FEATPROP.PLAN_SEGMENT_TYPE) != phase.value:
                end = f.getProp(FEATPROP.FLIGHT_PLAN_INDEX) - 1
                logger.debug(f"{phase.value} from {start} to {end}")
                return (start, end)
        logger.debug(f"no framing indices for {phase.value} (start={start})")
        return (start, None)

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
            # "MIN ALT",
            # "MAX ALT",
            # "ALT TARGET",
            # "MIN SPEED",
            # "MAX SPEED",
            # "SPEED TARGET",
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
                    (w.getRestrictionDesc() if hasattr(w, "hasRestriction") and w.hasRestriction() else ""),
                    round(d, 1),
                    round(total_dist),
                    # w.getProp("_alt_min"),
                    # w.getProp("_alt_max"),
                    # w.getProp("_alt_target"),
                    # w.getProp("_speed_min"),
                    # w.getProp("_speed_max"),
                    # w.getProp("_speed_target"),
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

    def next_above_alt_restriction(self, idx_start, max_distance: int | None = None) -> FeatureWithRestriction | None:
        """Used during climb"""
        fun = "hasAltitudeRestriction"
        last_point = self.flightplan_wpts[idx_start]
        total_dist = 0.0
        idx = idx_start + 1
        while idx < len(self.flightplan_wpts):
            w = self.flightplan_wpts[idx]
            d = distance(last_point, w)
            if hasattr(w, fun):
                func = getattr(w, fun)
                if func():
                    if w.alt_restriction_type in [" ", "+", "B", "G", "H", "I", "J", "V", "X"]:
                        # logger.debug(
                        #     f"idx {idx}: has alt restriction at or above {w.alt1} {w.getAltitudeRestrictionDesc()} ({w.alt_restriction_type in [' ','+']})"
                        # )
                        return w  # (w, d)
                    # else:
                    #     logger.debug(f"idx {idx}: has alt restriction {w.getAltitudeRestrictionDesc()} ({w.alt_restriction_type in [' ','+']})")
            idx = idx + 1
            last_point = w
            total_dist = total_dist + d
            if max_distance is not None and total_dist > max_distance:
                logger.debug(f"has no alt restriction before {round(total_dist, 2)}km (req. {round(max_distance, 2)}km)")
                return None
        return None

    def next_above_alt_restriction_idx(self, idx_start, idx_end) -> FeatureWithRestriction | None:
        """Used during desdend"""
        fun = "hasAltitudeRestriction"
        idx = idx_start + 1
        if idx_end == -1 or idx_end > (len(self.flightplan_wpts) - 1):
            idx_end = len(self.flightplan_wpts) - 1
        while idx <= idx_end:
            w = self.flightplan_wpts[idx]
            if hasattr(w, fun):
                func = getattr(w, fun)
                if func():
                    if w.alt_restriction_type in [" ", "+", "B", "G", "H", "I", "J", "V", "X"]:
                        # logger.debug(
                        #     f"idx {idx}: has alt restriction at or below {w.alt1} {w.getAltitudeRestrictionDesc()} ({w.alt_restriction_type in [' ','-']})"
                        # )
                        return w  # (w, d)
                    # else:
                    #     logger.debug(f"idx {idx}: has alt restriction {w.getAltitudeRestrictionDesc()} ({w.alt_restriction_type in [' ','-']})")
            idx = idx + 1
        return None

    def next_below_alt_restriction(self, idx_start, max_distance: int | None = None) -> FeatureWithRestriction | None:
        """Used during desdend"""
        fun = "hasAltitudeRestriction"
        last_point = self.flightplan_wpts[idx_start]
        total_dist = 0.0
        idx = idx_start + 1
        while idx < len(self.flightplan_wpts):
            w = self.flightplan_wpts[idx]
            d = distance(last_point, w)
            if hasattr(w, fun):
                func = getattr(w, fun)
                if func():
                    if w.alt_restriction_type in [" ", "-", "B", "G", "H", "I", "J", "X", "Y"]:
                        # logger.debug(
                        #     f"idx {idx}: has alt restriction at or above {w.alt1} {w.getAltitudeRestrictionDesc()} ({w.alt_restriction_type in [' ','+']})"
                        # )
                        return w  # (w, d)
                    # else:
                    #     logger.debug(f"idx {idx}: has alt restriction {w.getAltitudeRestrictionDesc()} ({w.alt_restriction_type in [' ','+']})")
            idx = idx + 1
            last_point = w
            total_dist = total_dist + d
            if max_distance is not None and total_dist > max_distance:
                logger.debug(f"has no alt restriction before {round(total_dist, 2)}km (req. {round(max_distance, 2)}km)")
                return None
        return None

    def next_below_alt_restriction_idx(self, idx_start, idx_end) -> FeatureWithRestriction | None:
        """Used during climb"""
        fun = "hasAltitudeRestriction"
        idx = idx_start + 1
        if idx_end == -1:
            idx_end = len(self.flightplan_wpts)
        while idx <= idx_end:
            w = self.flightplan_wpts[idx]
            if hasattr(w, fun):
                func = getattr(w, fun)
                if func():
                    if w.alt_restriction_type in [" ", "-", "B", "G", "H", "I", "J", "X", "Y"]:
                        # logger.debug(
                        #     f"idx {idx}: has alt restriction at or below {w.alt1} {w.getAltitudeRestrictionDesc()} ({w.alt_restriction_type in [' ','-']})"
                        # )
                        return w  # (w, d)
                    # else:
                    #     logger.debug(f"idx {idx}: has alt restriction {w.getAltitudeRestrictionDesc()} ({w.alt_restriction_type in [' ','-']})")
            idx = idx + 1
        return None

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
