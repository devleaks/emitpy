"""
A succession of positions where the aircraft passes. Includes taxi and takeoff or landing and taxi.
"""
import os
import io
import json
import logging
import copy
from math import pi
from datetime import datetime, timedelta

from tabulate import tabulate

from emitpy.geo.turf import LineString, FeatureCollection, Feature, saveGeoJSON
from emitpy.airspace import Restriction, NamedPoint
from emitpy.geo.turf import distance, destination, bearing
from emitpy.flight import Flight, FLIGHT_SEGMENT
from emitpy.airport import ManagedAirportBase
from emitpy.aircraft import ACPERF
from emitpy.geo import MovePoint, Movement
from emitpy.geo import moveOn, cleanFeatures, asLineString, toKML, adjust_speed_vector, toSO6
from emitpy.graph import Route
from emitpy.utils import compute_headings, show_path
from emitpy.constants import POSITION_COLOR, FEATPROP, TAXI_SPEED, SLOW_SPEED, INITIAL_CLIMB_SAFE_ALT_M, FINAL_APPROACH_FIX_ALT_M
from emitpy.constants import FLIGHT_DATABASE, FLIGHT_PHASE, FILE_FORMAT, MOVE_TYPE
from emitpy.parameters import MANAGED_AIRPORT_AODB
from emitpy.message import FlightMessage
from emitpy.utils import interpolate as doInterpolation, compute_time as doTime, convert
from .standardturn import standard_turn_flyby, standard_turn_flyover

logger = logging.getLogger("FlightMovement")

has_top_of_descend = False


class Altitude:
    """Restrictions and CIFP uses imperial units. Emitpy uses Système International.
    We need both unit systems in FlightMovement.
    """

    NO_ALTITUDE_VALUE = -99999  # none for altitude

    def __init__(self, meters: float = 0) -> None:
        """altitude is in meters"""
        self.altitude = meters

    def __str__(self):
        return f"{round(self.altitude, 1)}m, {int(self.in_ft)}ft"

    @property
    def in_m(self) -> float:
        return self.altitude

    @property
    def in_ft(self) -> float:
        return convert.meters_to_feet(self.altitude)

    @in_m.setter
    def in_m(self, meters: float):
        self.altitude = meters

    @in_ft.setter
    def in_ft(self, feet: float):
        self.altitude = convert.feet_to_meters(feet)


class Distance:
    """Restrictions and CIFP uses imperial units. Emitpy uses Système International.
    We need both unit systems in FlightMovement.
    """

    def __init__(self, km: float = 0) -> None:
        """altitude is in meters"""
        self.distance = km

    def __str__(self):
        return f"{round(self.distance, 1)}km, {round(self.in_nm, 1)}nm"

    @property
    def in_km(self) -> float:
        return self.distance

    @property
    def in_nm(self) -> float:
        return convert.m_to_nm(self.distance)

    @in_km.setter
    def in_km(self, km: float):
        self.distance = km

    @in_nm.setter
    def in_nm(self, nm: float):
        self.distance = convert.nm_to_meters(nm)


class VSpeed:
    """Restrictions and CIFP uses imperial units. Emitpy uses Système International.
    We need both unit systems in FlightMovement.
    """

    def __init__(self, ms: float = 0) -> None:
        """vpseed in meters/second"""
        self.vspeed = ms

    def __str__(self):
        return f"{round(self.vspeed, 1)}m/s, {int(self.in_fpm)}ft/min"

    @property
    def in_ms(self) -> float:
        return self.vspeed

    @property
    def in_fpm(self) -> float:
        return convert.ms_to_fpm(self.vspeed)

    @in_ms.setter
    def in_ms(self, ms: float):
        self.vspeed = ms

    @in_fpm.setter
    def in_fpm(self, fpm: float):
        self.vspeed = convert.fpm_to_ms(fpm)


class Speed:
    """Restrictions and CIFP uses imperial units. Emitpy uses Système International.
    We need both unit systems in FlightMovement.
    """

    def __init__(self, ms: float = 0) -> None:
        """vpseed in meters/second"""
        self.speed = ms

    def __str__(self):
        return f"{round(self.speed, 1)}m/s, {int(self.in_kn)}kn"

    @property
    def in_ms(self) -> float:
        return self.speed

    @property
    def in_kn(self) -> float:
        return convert.ms_to_kn(self.speed)

    @in_ms.setter
    def in_ms(self, ms: float):
        self.speed = ms

    @in_kn.setter
    def in_kn(self, kn: float):
        self.speed = convert.kn_to_ms(kn)


class FlightMovement(Movement):
    """
    Movement build the detailed path of the aircraft, both on the ground (taxi) and in the air,
    from takeoff to landing and roll out.
    """

    def __init__(self, flight: Flight, airport: ManagedAirportBase):
        Movement.__init__(self, airport=airport, reason=Flight)
        self.flight = flight
        self.flight_id = self.flight.getId()
        self.is_arrival = self.flight.is_arrival()
        self.pauses = {}  # Dict of "variable" pauses that can be added to point: "pause-name": {Feature-properties-select}
        self._premoves = []  # Array of Features<Point>, pre-move is before standard turn applied
        self.takeoff_hold = None
        self.end_rollout = None
        self.holdingpoint = None
        self.taxipos = []  # Array of Features<Point>
        self.tows = []  # list of tow movements
        self.flight.set_movement(self)

    @staticmethod
    def create(flight: Flight, airport: ManagedAirportBase):
        # Allows to expose Movement without exposing ArrivalMove or DepartureMove
        if flight.is_arrival():
            return ArrivalMove(flight, airport)
        return DepartureMove(flight, airport)

    def getId(self):
        return self.flight.getId()

    def getInfo(self):
        return {
            "type": MOVE_TYPE.FLIGHT.value,  # type(self).__name__
            "ident": self.getId(),
            "flight": self.flight.getInfo(),
            "icao24": self.flight.getInfo()["icao24"],
        }

    def getSource(self):
        # Abstract class
        return self.flight

    def move(self):
        """
        Chains local function calls to do the work.
        """
        logger.debug("moving..")
        logger.debug("..compute vertical navigation..")
        status = self.vnav()
        if not status[0]:
            logger.warning(status[1])
            return status

        logger.debug(self.tabulateFlightMovement("UNTIMED FLIGHT PLAN"))

        # #####################################################
        #
        #
        # logger.debug(f"flight {len(self.getMovePoints())} points, taxi {len(self.taxipos)} points")
        # return (False, "FlightMovement::TEMPORARY completed")
        #
        #
        # #####################################################

        logger.debug("..compute standard turns..")
        status = self.standard_turns()
        if not status[0]:
            logger.warning(status[1])
            return status

        if self.flight.is_arrival():
            logger.debug("..add TMO..")
            status = self.add_tmo()
            if not status[0]:
                logger.warning(status[1])
                return status

            status = self.add_faraway()
            if not status[0]:
                logger.warning(status[1])
                return status

        logger.debug("..interpolate..")
        status = self.interpolate()
        if not status[0]:
            logger.warning(status[1])
            return status

        logger.debug("..compute course..")
        res = compute_headings(self.getMovePoints())
        if not res[0]:
            logger.warning(status[1])
            return res

        # print([f.course() for f in self.getMovePoints()])

        logger.debug("..compute time..")
        status = self.time()  # sets the time for gross approximation
        if not status[0]:
            logger.warning(status[1])
            return status

        duration0 = self.getMovePoints()[-1].time()
        logger.debug(f"flight duration without winds: {duration0}")

        tb = []
        for p in self.getMovePoints():
            tb.append(p.time())

        logger.debug("..add wind..")
        status = self.add_wind()  # refines speeds
        if not status[0]:
            logger.warning(status[1])
            return status

        logger.debug("..compute time with wind..")
        status = self.time()  # sets the time for wind adjusted speed
        if not status[0]:
            logger.warning(status[1])
            return status

        ta = []
        for p in self.getMovePoints():
            ta.append(p.time())

        # cumul = 0
        # for i in range(len(tb)):
        #     diff = tb[i]-ta[i]
        #     logger.debug(f"{i}: {tb[i]} {ta[i]} {diff}")

        duration = self.getMovePoints()[-1].time()
        logger.debug(f"flight duration with winds: {duration} ({timedelta(seconds=round(duration))} + {timedelta(seconds=round(duration - duration0))})")
        self.flight.estimate_opposite(travel_time=duration)

        logger.debug("..add taxi..")
        status = self.taxi()
        if not status[0]:
            logger.warning(status[1])
            return status

        status = self.taxiInterpolateAndTime()
        if not status[0]:
            logger.warning(status[1])
            return status
        # printFeatures(self.taxipos, "after taxi")

        logger.debug(self.tabulateFlightMovement("FLIGHT MOVEMENT"))

        logger.debug(self.tabulateFlightPlan())

        logger.debug("..moved")
        logger.debug(f"flight {len(self.getMovePoints())} points, taxi {len(self.taxipos)} points")
        return (True, "FlightMovement::move completed")

    def saveFile(self, **kwargs):
        """
        Save flight paths to 3 files for flight plan, detailed movement, and taxi path.
        Save a technical json file which can be loaded later, and GeoJSON files for display.
        @todo should save file format version number.
        """
        basename = os.path.join(MANAGED_AIRPORT_AODB, FLIGHT_DATABASE, self.flight_id)

        def saveMe(arr, name):
            # filename = os.path.join(basename + "-" + name + ".json")
            # with open(filename, "w") as fp:
            #     json.dump(arr, fp, indent=4)

            filename = os.path.join(basename + "-" + name + ".geojson")
            fc = cleanFeatures(arr)
            # first = True
            # for f in fc:
            #     if first:
            #         print(type(f), f.__dict__, type(f.geometry), f.geometry.__dict__)
            #         first = False
            saveGeoJSON(filename, FeatureCollection(features=fc))

        # saveMe(self.flight.flightplan_wpts, "1-plan")
        if kwargs.get("plan"):
            if len(self.flight.flightplan_wpts) > 1:
                ls = Feature(geometry=asLineString(self.flight.flightplan_wpts))
                saveMe(self.flight.flightplan_wpts + [ls], FILE_FORMAT.FLIGHT_PLAN.value)

        # saveMe(self._premoves, "2-flight")
        if kwargs.get("flight"):
            if len(self._premoves) > 1:
                ls = Feature(geometry=asLineString(self._premoves))
                saveMe(self._premoves + [ls], FILE_FORMAT.FLIGHT.value)

        # saveMe(self.getMovePoints(), "3-move")
        move_points = self.getMovePoints()
        if len(move_points) > 1:
            if kwargs.get("move"):
                ls = Feature(geometry=asLineString(move_points))
                saveMe(move_points + [ls], FILE_FORMAT.MOVE.value)

            if kwargs.get("kml"):
                kml = toKML(cleanFeatures(move_points), name=self.flight.getId(), desc=str(self.flight))
                filename = os.path.join(basename + FILE_FORMAT.MOVE.value + ".kml")
                with open(filename, "w") as fp:
                    fp.write(kml)
                    logger.debug(f"saved kml {show_path(filename)} ({len(move_points)})")

        # saveMe(self.taxipos, "4-taxi")
        if kwargs.get("taxi"):
            if len(self.taxipos) > 1:
                ls = Feature(geometry=asLineString(self.taxipos))
                saveMe(self.taxipos + [ls], FILE_FORMAT.TAXI.value)

        logger.debug(f"saved {self.flight_id}")
        return (True, "Movement::save saved")

    def load(self):
        """
        Load flight paths from 3 files for flight plan, detailed movement, and taxi path.
        File must be saved by above saveFile() function.
        """
        basename = os.path.join(MANAGED_AIRPORT_AODB, FLIGHT_DATABASE, self.flight_id)

        filename = os.path.join(basename, FILE_FORMAT.FLIGHT_PLAN.value)
        with open(filename, "r") as fp:
            self._premoves = json.load(fp)

        filename = os.path.join(basename, FILE_FORMAT.FLIGHT.value)
        with open(filename, "r") as fp:
            self._premoves = json.load(fp)

        filename = os.path.join(basename, FILE_FORMAT.MOVE.value)
        with open(filename, "r") as fp:
            self.setMovePoints(json.load(fp))

        filename = os.path.join(basename, FILE_FORMAT.TAXI.value)
        with open(filename, "r") as fp:
            self.taxipos = json.load(fp)

        logger.debug("loaded %d " % self.flight_id)
        return (True, "Movement::load loaded")

    def snav(self):
        """
        Perform speed control for route.
        Must be run on _premove points.
        For each wp, check speed constraints.
        If not respected:
        - adjusts speed BEFORE the constraint, upto the previous constraints when climbing,
        - adjust speed AFTER the constraint,upto the previous constraints when descending.
        """
        fc = self._premoves

        # Fill in missing speeds
        last_speed = 0
        for f in fc:
            s = f.speed()
            if s is None:
                f.setSpeed(last_speed)
            else:
                last_speed = s

        last_sr = 3  # 0=hold, 1=take-off, 2=initial climb, cannot reduce speed of initial climb
        idx = 3
        cruise = False
        while idx < (len(fc) - 2) and not cruise:
            w = fc[idx]
            if w.getMark() in [FLIGHT_PHASE.INITIAL_CLIMB.value]:
                last_sr = max(last_sr, w.getProp(FEATPROP.PREMOVE_INDEX))

            restriction = w.getProp("restriction")
            # logger.debug(f"{idx}: {restriction}")
            if restriction is not None and restriction != "":  # has restriction...
                r = Restriction.parse(restriction)
                logger.debug(f"doing {r.getRestrictionDesc()}..")
                if w.speed() is not None and not r.checkSpeed(w):
                    r.adjustSpeed(w)

                    start_idx = w.getProp(FEATPROP.PREMOVE_INDEX)
                    logger.debug(f"restricting backward ({start_idx}->{last_sr})..")
                    for idx in range(start_idx - 1, last_sr - 1, -1):
                        w = fc[idx]
                        r.adjustSpeed(w)
                    last_sr = w.getProp(FEATPROP.PREMOVE_INDEX)
                    logger.debug(f"..restricted")
                else:
                    logger.debug(f"..restriction ok {r.getRestrictionDesc()}")
                logger.debug(f"..done")
            if w.getMark() in [FLIGHT_PHASE.CRUISE.value, FLIGHT_PHASE.TOP_OF_ASCENT.value]:
                logger.debug(f"start of cruise at {idx}")
                cruise = True
            idx = idx + 1

        while cruise:
            w = fc[idx]
            if w.getMark() not in [FLIGHT_PHASE.CRUISE.value, FLIGHT_PHASE.TOP_OF_ASCENT.value, "reached_cruise_speed", "end_of_decelerate"]:
                logger.debug(f"end of cruise at {idx} ({w.getMark()})")
                cruise = False
            #
            # Should here handle cruise speed restrictions if any
            #
            idx = idx + 1

        idx = idx - 1  # we start at end of cruise, fc[-1]=end-of-roll, fc[-2]=touch-down, fc[-3]=final fix
        while idx < (len(fc) - 2):
            w = fc[idx]

            restriction = w.getProp("restriction")
            # logger.debug(f"{idx}: {restriction}")
            if restriction is not None and restriction != "":  # has restriction...
                r = Restriction.parse(restriction)
                logger.debug(f"doing {r.getRestrictionDesc()}..")
                if w.speed() is not None and not r.checkSpeed(w):
                    r.adjustSpeed(w)
                    # Find next restriction
                    logger.debug(f"restricting forward..")
                    next_restriction = False
                    idx = idx + 1
                    # adjust speed forward until next speed restriction
                    while not next_restriction and idx < len(fc):
                        w = fc[idx]
                        restriction2 = w.getProp("restriction")
                        if restriction2 is not None and restriction2 != "":
                            r2 = Restriction.parse(restriction2)
                            if r2.hasSpeedRestriction():
                                if r.restricted_speed > r2.restricted_speed:  # never re-accelerate
                                    next_restriction = True
                                    idx = idx - 1
                        if not next_restriction:
                            r.adjustSpeed(w)
                            idx = idx + 1
                    logger.debug(f"..restricted to {idx}")
                else:
                    logger.debug(f"restriction ok {r.getRestrictionDesc()}")
                logger.debug(f"..done")
            idx = idx + 1

    def vnav(self):
        """
        Perform vertical navigation for route
        @todo: Add optional hold

        Note: Flight plan will be in fc.
        fc[0] is the departure airport.
        fc[-1] is the arrival airport
        Trip is fc[1:-1]

        By far the most difficult procedure of the whole emitpy package,
        especially since it attempts to respects procedures.

        """
        fpln = self.flight.flightplan_wpts
        if fpln is None or len(fpln) == 0:
            logger.warning("no flight plan")
            return (False, "Movement::vnav no flight plan, cannot move")

        ac = self.flight.aircraft
        actype = ac.actype
        # actype.perfs()
        is_grounded = True
        depapt_alt = Altitude()
        arrapt_alt = Altitude()

        def fpi(f) -> int:
            return int(f.getProp(FEATPROP.FLIGHT_PLAN_INDEX))

        def already_copied(index):
            x = list(filter(lambda f: f.getProp(FEATPROP.FLIGHT_PLAN_INDEX) == index, self._premoves))
            return len(x) > 0

        def addCurrentpoint(arr, pos, oi, ni, color, mark, reverse: bool = False):
            # catch up adding all points in flight plan between oi, ni
            # then add pos (which is between ni and ni+1)
            # logger.debug("%d %d %s" % (oi, ni, reverse))
            if oi != ni:
                for idx in range(oi + 1, ni + 1):
                    i = idx if not reverse else len(fpln) - idx - 1
                    wpt = fpln[i]
                    p = MovePoint.new(wpt)
                    logger.debug(
                        f"addCurrentpoint:{'(rev)' if reverse else ''} adding {p.getProp(FEATPROP.PLAN_SEGMENT_TYPE)} {p.getProp(FEATPROP.PLAN_SEGMENT_NAME)} ({fpi(p)})"
                    )
                    p.setColor(color)
                    p.setMark(mark)
                    p.setProp(FEATPROP.FLIGHT_PLAN_INDEX, i)
                    p.setColor(POSITION_COLOR.FLIGHT_PLAN.value)  # remarkable point in GREEN
                    p.copy_restriction_from(wpt)
                    # print(f"****C adding idx={len(arr)}, pt={i}, f={wpt.getProp(FEATPROP.PLAN_SEGMENT_TYPE)}, alt={wpt.altitude()}m, mark={mark}")
                    arr.append(p)
            arr.append(pos)
            # logger.debug("adding remarkable point: %s (%d)" % (pos.getProp(FEATPROP.MARK), len(coll)))
            # logger.debug("return index: %d" % (ni))
            # we now are at pos which is on LineString after index ni
            return ni

        def addIntermediatePoint(arr, propname: FEATPROP, value: float, go_up: bool) -> MovePoint | None:
            last_value = 0
            for f in arr:
                currval = f.getProp(propname)
                if go_up and currval > value or not go_up and currval < value:
                    # interpolate between last_val and f
                    delta = f.getProp(propname) - currval
                    d = distance(last_value, f)
                    pct = (currval - value) / delta
                    brg = bearing(last_value, f)
                    pt = destination(last_value, length=pct * d, course=brg)
                    newpos = MovePoint.new(pt)
                    newpos.setMark(f"intermediate point for {propname.value} at {value}")
                    return newpos
                last_value = f
            return None

        def addMovepoint(arr, src, alt, speed, vspeed, color, mark, ix):
            # create a copy of src, add properties on copy, and add copy to arr.
            # logger.debug(f"{mark} {ix}, s={speed}")
            geom = None
            if type(src) == dict:
                geom = src["geometry"]
            else:
                geom = src.geometry
            mvpt = MovePoint(geometry=geom, properties={})
            mvpt.setAltitude(alt)
            mvpt.setSpeed(speed)
            mvpt.setVSpeed(vspeed)
            mvpt.setColor(color)
            mvpt.setMark(mark)
            mvpt.setProp(FEATPROP.FLIGHT_PLAN_INDEX, ix)
            mvpt.setProp(FEATPROP.GROUNDED, is_grounded)
            mvpt.copy_restriction_from(src)
            # print(f"****M adding idx={len(arr)}, pt={ix}, f=, alt={alt}m, mark={mark}")
            arr.append(mvpt)
            return mvpt

        def moveOnLS(coll, reverse, fc, fcidx, currpos, dist, alt, speed, vspeed, color, mark, mark_tr):
            # move on dist (meters) on linestring from currpos (which is between fcidx and fcidx+1)
            # returns position after dist and new index, new position p is between newidx and newidx+1
            p, newidx = moveOn(fc, fcidx, currpos, dist)
            # logger.debug(f"moveOnLS:{'(rev)' if reverse else ''} from {fcidx} to {newidx} ({mark}), s={speed}")
            # from currpos after dist we will be at newpos
            newpos = MovePoint.new(p)
            newpos.setAltitude(alt)
            newpos.setSpeed(speed)
            newpos.setVSpeed(vspeed)
            newpos.setColor(color)
            newpos.setMark(mark)
            return (newpos, addCurrentpoint(arr=coll, pos=newpos, oi=fcidx, ni=newidx, color=color, mark=mark_tr, reverse=reverse))

        def climb_to_alt(
            start_idx, current_altitude, target_altitude, target_index, do_it: bool = True, expedite: bool = False, comment: str | None = None
        ) -> tuple[int, int]:
            """Compute distance necessary to reach target_altitude.
            From that distance, compute framing flight plan indices (example: between 6 and 7).
            Returns the last index (7). At index 7, we will be at target_altitude.

            Climbs from current_position at current_altitude to new position at target altitude.
            if expedite climb, climb first to target_altitude and then fly level to waypoint
            if not expedite, climb at regular pace to target_altitude at waypoint.

            returns:
             - New position, which is a way point with restriction or top of climb
             - New altitude at waypoint (after climbing)
            """

            if target_altitude < current_altitude:
                logger.debug("climb to alt: need to descend")
                return descend_to_alt(start_idx, current_altitude, target_altitude, target_index, do_it, expedite)

            if target_altitude == current_altitude:
                logger.debug("same altitude, no need to climb")
                # return (target_index, target_altitude)

            delta = target_altitude - current_altitude
            # ranges are initial-climb, climb-150, climb-240, climb-cruise
            # we assume we are above initial climb, we can also safely assure
            # that we are below FL150 for SID and STAR, but let's check it
            if actype.getClimbSpeedRangeForAlt(convert.feet_to_meters(current_altitude)) != actype.getClimbSpeedRangeForAlt(
                convert.feet_to_meters(target_altitude)
            ):
                logger.warning(f"change of ranges for altitudes {current_altitude} -> {target_altitude}")

            roc = actype.getROCDistanceForAlt(
                convert.feet_to_meters(target_altitude if do_it else current_altitude)
            )  # special when we suspect we climb to cruise
            min_dist_to_climb = (convert.feet_to_meters(ft=delta) / roc) / 1000  # km
            logger.debug(f"need distance {round(min_dist_to_climb, 2)} km to climb")
            total_dist = 0
            curridx = start_idx  # we just get an idea from the difference in altitude and the distance to travel, no speed/time involved
            while total_dist < min_dist_to_climb and curridx < (len(fpln) - 2):  # last point is airport
                d = distance(fpln[curridx], fpln[curridx + 1])
                total_dist = total_dist + d
                curridx = curridx + 1
                # print(">>>", curridx, d, total_dist)

            logger.debug(f"can climb from {current_altitude} at idx {start_idx} to {target_altitude} before idx {curridx} (at {round(total_dist, 2)} km)")

            if not do_it:
                logger.debug(f"just getting index for climb from {current_altitude} to {target_altitude}, no altitude change")
                return (curridx, target_altitude)

            # we are now at fpln[curridx], at altitude target_altitude, two ways to get there
            if curridx > target_index:  # this means there will be a Restriction violation
                logger.warning(f"at idx={start_idx}: cannot climb {delta}ft before requested index {target_index}")
                logger.warning(f"restriction violation")

            if expedite:
                logger.debug(f"expedite: will climb from {current_altitude}ft at idx {start_idx} to {target_altitude}ft at idx {curridx}")
            else:  # regular gradient climb
                logger.debug(
                    f"no expedite: will climb from {current_altitude}ft at idx {start_idx} to {target_altitude}ft at idx {curridx}, (has {round(total_dist, 2)} km to climb)"
                )
                curridx = max(curridx, target_index)
                currpos = None
                currdist = 0
                # special case: we do not copy the first point (airport)
                if start_idx == 0:
                    start_idx = 1
                for idx in range(start_idx, curridx):
                    speed = Speed()
                    vspeed = VSpeed()
                    localalt = Altitude()
                    localalt.in_ft = current_altitude
                    if delta != 0 and total_dist != 0:
                        localalt.in_ft = current_altitude + delta * (currdist / total_dist)
                    speed.in_ms, vspeed.in_ms = actype.getClimbSpeedAndVSpeedForAlt(localalt.in_m)
                    speed.in_ms = actype.low_alt_max_speed(alt=localalt.in_m, speed=speed.in_ms)
                    d = distance(fpln[idx], fpln[idx + 1])
                    logger.debug(", ".join([f"no expedite climb: at idx {idx}", f"alt={localalt}", f"speed={speed}", f"vspeed={vspeed}", f"d={round(d, 0)})"]))
                    currpos = addMovepoint(
                        arr=self._premoves,
                        src=fpln[idx],
                        alt=localalt.in_m,
                        speed=speed.in_ms,
                        vspeed=vspeed.in_ms,
                        color=POSITION_COLOR.CLIMB.value,
                        mark=FLIGHT_PHASE.CLIMB.value,
                        ix=idx,
                    )
                    if comment is not None:
                        currpos.setComment(comment)
                    currdist = currdist + d
                    # print(">>>", cidx, d, total_dist)
                # for fun
                # d = reduce(distance, fpln[start_idx:curridx], 0.0)

            return (curridx, target_altitude)

        def descend_to_alt(
            current_index, current_altitude, target_altitude, target_index, expedite: bool = True, comment: str | None = None
        ) -> tuple[int, int]:
            """Descend from current altitude to target. Expedite if necessary (i.e. always successds).
            From that distance, compute framing flight plan indices (example: between 6 and 7).
            Returns the last index (7). At index 7, we will be at target_altitude.
            """
            global has_top_of_descend
            MAX_TOD = 100  # km from airport, about 54nm, will descend at max. MAX_TOD km from arrival airport

            if target_altitude > current_altitude:
                logger.debug("descend to alt: need to climb")  # don't know if we can simply do this...
                return climb_to_alt(
                    start_idx=current_index,
                    current_altitude=current_altitude,
                    target_altitude=target_altitude,
                    target_index=target_index,
                    do_it=True,
                    expedite=expedite,
                    comment=comment,
                )

            if target_altitude == current_altitude:
                logger.debug("same altitude, no need to descend")

            delta = current_altitude - target_altitude

            if actype.getDescendSpeedRangeForAlt(current_altitude) != actype.getDescendSpeedRangeForAlt(target_altitude):
                logger.warning(f"change of ranges for altitudes {current_altitude} -> {target_altitude}")

            rod = actype.getRODDistanceForAlt(convert.feet_to_meters(current_altitude))  # we descend as fast as current altitude allows it
            min_dist_to_descend = (convert.feet_to_meters(ft=delta) / rod) / 1000  # km
            # logger.debug(f"ROD {rod} at {current_altitude}, need distance {round(min_dist_to_descend, 2)} km to descend")
            # Rule of thumb formula: (3 x height) + (1nm per 10kts of speed loss) + (1nm per 10kts of Tailwind Component)
            # 10kts = 5.144444 m/s
            # Tailwind: add 10nm for safety
            #
            # Speed goes from cruise speed to approach speed:
            if min_dist_to_descend > MAX_TOD:
                contrib_m = actype.descend_rate(altitude=convert.feet_to_meters(current_altitude), delta=convert.feet_to_meters(delta))  # in meters
                speed = Speed()
                vspeed = VSpeed()
                speed.in_ms, vspeed.in_ms = actype.getDescendSpeedAndVSpeedForAlt(convert.feet_to_meters(current_altitude))
                new_rod = convert.feet_to_meters(delta) / (MAX_TOD * 1000)
                fpm = convert.ms_to_fpm(ms=vspeed.in_ms * new_rod / rod)
                logger.info(
                    f"descend too long ({round(min_dist_to_descend, 2)} km, ROD={round(rod,4)}), will expedite to {round(convert.m_to_nm(m=MAX_TOD), 0)}nm (ROD={round(new_rod,4)}, or {round(fpm, 0)}ft/min)"
                )
                min_dist_to_descend = MAX_TOD

            # we start at target index and go backward until we have enough distance to descend
            total_dist = 0
            curridx = target_index
            target_dist = 0
            while total_dist < min_dist_to_descend and curridx > 0:
                d = distance(fpln[curridx - 1], fpln[curridx])
                total_dist = total_dist + d
                if curridx == current_index:
                    target_dist = total_dist
                curridx = curridx - 1
                # print(">>>!!!", current_index, "->", target_index, curridx, d, total_dist, min_dist_to_descend, target_dist)

            if target_altitude == current_altitude:  # special case, level flight, no need to descend
                # in this case above total_dist = 0 since alt requirement satisfied at target
                logger.debug(f"no need to descend, must add all points between {current_index} and {target_index}")
                curridx = current_index

            logger.debug(
                f"should start descend from {current_altitude} at {curridx} (current position is {current_index}) to reach {target_altitude}ft at {target_index}: {delta}ft in {round(total_dist,1)}km (target={round(target_dist,1)}km)"
            )

            # we are now at fpln[curridx] and we can descend to target_altitude at target_index
            # If fpln[curridx] is before fpln[current_index], it means that from the current_index we cannot descend to the target_altitude (unless we expedite)
            # We may got before current_index only in one case: when we search the top_of_descend from where we have to initiate our descend.
            total_dist = 0
            if curridx < current_index and has_top_of_descend:  # this means there will be a Restriction violation
                logger.warning(
                    f"at {current_index}: cannot descend {delta}ft from {current_index} before requested index {target_index}, should start at {curridx}"
                )
                logger.warning(f"restriction violation")
                if expedite:
                    total_dist = target_dist
                    curridx = current_index
                    logger.warning(
                        f"will expedite descend from {current_altitude}ft at idx {current_index} to {target_altitude}ft at {target_index}, available distance is {round(total_dist)}km"
                    )
                else:
                    logger.warning(f"ignoring restriction")
                    curridx = current_index  # if we have a TOD, we cannot go further back than current_index
                    for idx in range(curridx, target_index):
                        total_dist = total_dist + distance(fpln[idx], fpln[idx + 1])
            else:
                # for fun
                # d = reduce(distance, fpln[current_index:curridx], 0.0)
                # recalculate total_dist for smooth descend:
                for idx in range(curridx, target_index):
                    total_dist = total_dist + distance(fpln[idx], fpln[idx + 1])
                logger.debug(
                    f"will descend from {current_altitude}ft at idx {curridx} to {target_altitude}ft at {target_index}, available distance is {round(total_dist)}km (no expedite)"
                )
            if total_dist == 0:
                logger.warning(f"total distance is zero, is it the same waypoint?, or may be level flight?")
                # return (target_index, target_altitude)

            curridx = min(curridx, target_index)
            currpos = None
            currdist = 0
            # print(">>>>", delta, total_dist, current_index, current_altitude, target_index, target_altitude)
            logger.debug(f"rate: {round(delta, 0)}ft/{round(total_dist, 0)}km")
            for idx in range(curridx, min(target_index + 1, len(fpln) - 1)):
                d = distance(fpln[idx], fpln[idx + 1])
                if already_copied(idx):  # the first point may be the last point of the previous call here
                    currdist = currdist + d
                    continue
                speed = Speed()
                vspeed = VSpeed()
                localalt = Altitude()
                localalt.in_ft = current_altitude
                if delta != 0 and total_dist != 0:
                    localalt.in_ft = current_altitude - delta * (currdist / total_dist)
                speed.in_m, vspeed.in_m = actype.getDescendSpeedAndVSpeedForAlt(localalt.in_m)
                speed.in_m = actype.low_alt_max_speed(alt=localalt.in_m, speed=speed.in_m)
                # print(">>>>>", idx, alt, alt_in_m, speed, vspeed, convert.ms_to_kn(speed, 0), convert.ms_to_fpm(vspeed, 0))
                logger.debug(
                    ", ".join(
                        [
                            f"no expedite descend: at idx {idx}",
                            f"dist={round(currdist, 0)}km",
                            f"alt={localalt}",
                            f"speed={speed}",
                            f"vspeed={vspeed}",
                            f"d={round(d, 0)}",
                        ]
                    )
                )
                if has_top_of_descend:
                    currpos = addMovepoint(
                        arr=self._premoves,
                        src=fpln[idx],
                        alt=localalt.in_m,
                        speed=speed.in_m,
                        vspeed=vspeed.in_m,
                        color=POSITION_COLOR.DESCEND.value,
                        mark=FLIGHT_PHASE.DESCEND.value,  # not correct, fpln[idx].getProp(FEATPROP.PLAN_SEGMENT_NAME)?
                        ix=idx,
                    )
                else:
                    currpos = addMovepoint(
                        arr=self._premoves,
                        src=fpln[idx],
                        alt=localalt.in_m,
                        speed=speed.in_m,
                        vspeed=vspeed.in_m,
                        color=POSITION_COLOR.DESCEND.value,
                        mark=FLIGHT_PHASE.TOP_OF_DESCENT.value,  # not correct, fpln[idx].getProp(FEATPROP.PLAN_SEGMENT_NAME)?
                        ix=idx,
                    )
                    has_top_of_descend = True
                if comment is not None:
                    currpos.setComment(comment)
                currdist = currdist + d

            logger.debug(
                ", ".join(
                    [
                        f"no expedite: completed descend from {current_altitude}ft at idx {curridx} to {target_altitude}ft at idx {target_index}",
                        f"({round(total_dist, 2)} km)",
                    ]
                )
            )

            return (target_index, target_altitude)

        def get_descend_start_index(min_index, current_altitude, target_index, target_altitude) -> int:
            """Compute distance necessary to reach target_altitude.
            From that distance, compute framing flight plan indices (example: between 6 and 7).
            Returns the last index (7). At index 7, we will be at target_altitude.
            """
            MAX_TOD = 100  # km from airport, about 54nm, will descend at max. MAX_TOD km from arrival airport

            if target_altitude == current_altitude:
                logger.debug("already at target altitude, no descend needed")
                return target_index

            delta = current_altitude - target_altitude

            if actype.getDescendSpeedRangeForAlt(current_altitude) != actype.getDescendSpeedRangeForAlt(target_altitude):
                logger.warning(f"change of ranges for altitudes {current_altitude} -> {target_altitude}")

            rod = actype.getRODDistanceForAlt(convert.feet_to_meters(current_altitude))  # we descend as fast as current altitude allows it
            min_dist_to_descend = (convert.feet_to_meters(ft=delta) / rod) / 1000  # km
            # logger.debug(f"ROD {rod} at {current_altitude}, need distance {round(min_dist_to_descend, 2)} km to descend")
            # Rule of thumb formula: (3 x height) + (1nm per 10kts of speed loss) + (1nm per 10kts of Tailwind Component)
            # 10kts = 5.144444 m/s
            # Tailwind: add 10nm for safety
            #
            # Speed goes from cruise speed to approach speed:
            if min_dist_to_descend > MAX_TOD:
                speed, vspeed = actype.getDescendSpeedAndVSpeedForAlt(convert.feet_to_meters(current_altitude))
                new_rod = convert.feet_to_meters(delta) / (MAX_TOD * 1000)
                fpm = convert.ms_to_fpm(ms=vspeed * new_rod / rod)
                logger.info(
                    f"descend too long ({round(min_dist_to_descend, 2)} km, ROD={round(rod,4)}), will expedite to {round(convert.m_to_nm(m=MAX_TOD), 0)}nm (ROD={round(new_rod,4)}, or {round(fpm, 0)}ft/min)"
                )
                min_dist_to_descend = MAX_TOD

            # we start at target index and go backward until we have enough distance to descend
            total_dist = 0
            candidate_idx = target_index
            while total_dist < min_dist_to_descend and candidate_idx > 0:
                d = distance(fpln[candidate_idx - 1], fpln[candidate_idx])
                total_dist = total_dist + d
                candidate_idx = candidate_idx - 1
                # print(">>>", candidate_idx, d, total_dist, min_dist_to_descend)

            if candidate_idx < min_index:
                logger.warning(f"cannot descend from {current_altitude} at idx {min_index} to {target_altitude} at idx {target_index}")
                logger.warning(f"restriction violation; must start descend at {candidate_idx} ({round(total_dist)}km)")
            # else:
            #     logger.debug(f"can descend from {current_altitude} at idx {candidate_idx} to {target_altitude} at idx {target_index} ({round(total_dist)}km)")

            return candidate_idx

        def altitude_at_index(candidate_idx: int, start_idx: int, start_alt: int, end_idx: int, end_alt: int) -> int:
            if not start_idx <= candidate_idx <= end_idx:
                logger.debug(f"index {candidate_idx} not in range [{start_idx},{end_idx}]")
                return 0
            delta = start_alt - end_alt
            total_dist = 0
            candid = {}
            candid[start_idx] = 0
            for idx in range(start_idx, end_idx):
                total_dist = total_dist + distance(fpln[idx], fpln[idx + 1])
                candid[idx + 1] = total_dist
            if total_dist == 0:  # same points?
                logger.debug(f"no distance, must be same point (to ignore)")
                return -1
            slope = delta / total_dist
            ret = int(start_alt - slope * candid[candidate_idx])
            # logger.debug(
            #     ", ".join(
            #         [
            #             f"candidate: from {start_idx} at {start_alt} to {end_idx} at {end_alt}",
            #             f"slope {round(slope, 5)}, total {round(total_dist, 0)}km",
            #             f"partial={round(candid[candidate_idx], 0)}km, hence {round(ret, 0)}ft",
            #         ]
            #     )
            # )
            return ret

        def add_cruise(start_idx, end_idx):
            """Note: currently not respecting airway constraints.
            But ready to do so.
            """
            previous_restriction = None

            for i in range(start_idx, end_idx):
                wpt = fpln[i]
                # logger.debug("adding cruise: %d %s" % (i, wpt.getProp(FEATPROP.PLAN_SEGMENT_TYPE)))
                #
                # Should here handle alt restrictions in cruise segments
                #
                #
                # 1. at WP, get airway segment to next WP
                # airspace = self.flight.managedAirport.airport.airspace  # that's far!
                # next_wp = fpln[i + 1]
                # src_id = wpt.getId()
                # dst_id = next_wp.getId()
                # airway = airspace.get_edge(src_id, dst_id)
                # restriction = airway.restriction if airway is not None and airway.has_restriction() else None

                # 2. if (alt? speed?) restriction in airway segment, add it to both ends of segment
                p = addMovepoint(
                    arr=self._premoves,
                    src=wpt,
                    alt=self.flight.getCruiseAltitude(),
                    speed=cruise_speed,
                    vspeed=0,
                    color=POSITION_COLOR.CRUISE.value,
                    mark=FLIGHT_PHASE.CRUISE.value,
                    ix=i,
                )
                # if restriction is not None:
                #     logger.debug(f"airway starting at {src_id} has restriction {restriction.getRestrictionDesc()}, ignored")
                #     # p.add_restriction(restriction)
                #     previous_restriction = restriction
                # if previous_restriction is not None:
                #     logger.debug(f"airway ending at {src_id} has restriction {previous_restriction.getRestrictionDesc()}, ignored")
                #     # p.add_restriction(previous_restriction)
                #     previous_restriction = None
            logger.debug(f"added cruise from {start_idx} to {end_idx}")

        #
        # ########################################################################################
        #
        logger.debug(f"{'*' * 30} {type(self).__name__}: {len(fpln)} points in flight plan {'*' * 30}")
        # for f in fpln:
        #     logger.debug("flight plan: %s" % (f.getProp(FEATPROP.PLAN_SEGMENT_TYPE)))

        #
        # ########################################################################################
        #
        # PART 1: FORWARD: From takeoff to top of climb
        #
        # For take off, altitude is AGL.
        #
        logger.debug(f"departure from {self.flight.departure.icao} " + "=" * 30)
        TOH_BLASTOFF = 0.2  # km, distance of take-off hold position from runway threshold
        groundmv = 0
        fcidx = 0
        rwy = None
        newidx = 0

        if self.flight.departure.has_rwys():  # take off self.flight.is_departure()
            if self.flight.is_departure():  # we are at the managed airport, we must use the selected runway
                rwy = self.flight.rwy
            else:
                rwy = self.flight.departure.selectRWY(self.flight)
                logger.debug(f"remote departure: using runway {rwy.name}")
            rwy_threshold = rwy.getPoint()
            alt = rwy_threshold.altitude()
            if alt is None:
                logger.warning(f"departure airport has no altitude: {rwy_threshold}")
                depapt_alt.in_m = 0
            else:
                depapt_alt.in_m = float(alt)

            brg = bearing(rwy_threshold, rwy.end.getPoint())
            takeoff_hold = destination(rwy_threshold, TOH_BLASTOFF, brg)
            logger.debug(f"departure from {rwy.name}, {brg:f}")

            p = addMovepoint(
                arr=self._premoves,
                src=takeoff_hold,
                alt=depapt_alt.in_m,
                speed=0,
                vspeed=0,
                color=POSITION_COLOR.TAKE_OFF_HOLD.value,
                mark=FLIGHT_PHASE.TAKE_OFF_HOLD.value,
                ix=0,
            )
            p.setComment("take-off hold")
            self.takeoff_hold = copy.deepcopy(p)  # we keep this special position for taxiing (end_of_taxi)
            logger.debug(f"takeoff hold at {rwy.name}, {TOH_BLASTOFF:f}")

            takeoff_distance = actype.getSI(ACPERF.takeoff_distance) * self.airport.runwayIsWet() / 1000  # must be km for destination()
            takeoff = destination(takeoff_hold, takeoff_distance, brg)

            p = addMovepoint(
                arr=self._premoves,
                src=takeoff,
                alt=depapt_alt.in_m,
                speed=actype.getSI(ACPERF.takeoff_speed),
                vspeed=actype.getSI(ACPERF.initial_climb_vspeed),
                color=POSITION_COLOR.TAKE_OFF.value,
                mark=FLIGHT_PHASE.TAKE_OFF.value,
                ix=0,
            )
            p.setComment("take-off")
            groundmv = takeoff_distance
            logger.debug(f"takeoff at {rwy.name}, {takeoff_distance:f}")

            self.addMessage(
                FlightMessage(
                    subject=f"ACARS: {ac.icao24} {FLIGHT_PHASE.TAKE_OFF.value} from {self.flight.departure.icao}",
                    flight=self,
                    sync=FLIGHT_PHASE.TAKE_OFF.value,
                    info=self.getInfo(),
                )
            )
            is_grounded = False
            #
            # FROM NOW ON, WE ARE IN THE AIR
            #
            # initial climb, commonly accepted to above 1500ft AGL
            #
            logger.debug("initialClimb")
            step = actype.initialClimb(depapt_alt.in_m)  # (t, d, altend)
            initial_climb_distance = step[1] / 1000  # km
            # find initial climb point

            # we climb on path to see if we reach indices...
            currpos, newidx = moveOn(fpln, fcidx, p, initial_climb_distance)
            # we ignore currpos for now, we will climb straight, we ignore points
            # between fcidx and newidx during initial climb...
            initial_climb = destination(takeoff, initial_climb_distance, brg)
            currpos = addMovepoint(
                arr=self._premoves,
                src=initial_climb,
                alt=step[2],  # !! err corrected 7FEB24, was =alt=dept(alt)
                speed=actype.getSI(ACPERF.initial_climb_speed),
                vspeed=actype.getSI(ACPERF.initial_climb_vspeed),
                color=POSITION_COLOR.INITIAL_CLIMB.value,
                mark="end_initial_climb",
                ix=newidx,
            )
            currpos.setComment("inital climb")
            logger.debug(f"initial climb end at index {newidx}, {round(initial_climb_distance,3)}km")
            # small control to see if next point on flight plan is AFTER end of initial climb
            ctrd = distance(fpln[newidx], fpln[newidx + 1])
            if initial_climb_distance > ctrd:
                logger.warning(f"initial climb finishes at {round(initial_climb_distance,3)}km after start of SID that finishes at {round(ctrd,3)}km")
            else:
                logger.debug(f"index {newidx + 1} at {round(ctrd,3)}km")
            groundmv = groundmv + initial_climb_distance
            # we ignore vertices between takeoff and initial_climb
            # we go in straight line and ignore self._premoves, skipping eventual points

        else:  # no runway, simpler departure
            deptapt = fpln[0]
            alt = deptapt.altitude()
            if alt is None:
                logger.warning(f"departure airport has no altitude: {deptapt}")
                depapt_alt.in_m = 0
            else:
                depapt_alt.in_m = float(alt)
            currpos = addMovepoint(
                arr=self._premoves,
                src=deptapt,
                alt=depapt_alt.in_m,
                speed=actype.getSI(ACPERF.takeoff_speed),
                vspeed=actype.getSI(ACPERF.initial_climb_vspeed),
                color=POSITION_COLOR.TAKE_OFF.value,
                mark=FLIGHT_PHASE.TAKE_OFF.value,
                ix=fcidx,
            )
            logger.debug("origin added first point")
            currpos.setComment("departing airport")

            self.addMessage(
                FlightMessage(
                    subject=f"ACARS: {ac.icao24} {FLIGHT_PHASE.TAKE_OFF.value} from {self.flight.departure.icao}",
                    flight=self,
                    sync=FLIGHT_PHASE.TAKE_OFF.value,
                    info=self.getInfo(),
                )
            )
            is_grounded = False

            # initial climb, commonly accepted to above 1500ft AGL
            logger.debug("initialClimb")
            step = actype.initialClimb(depapt_alt.in_m)  # (t, d, altend)
            # find initial climb point
            groundmv = step[1]

            currpos, newidx = moveOnLS(
                coll=self._premoves,
                reverse=False,
                fc=fpln,
                fcidx=fcidx,
                currpos=currpos,
                dist=step[1],
                alt=step[2],
                speed=actype.getSI(ACPERF.initial_climb_speed),
                vspeed=actype.getSI(ACPERF.initial_climb_vspeed),
                color=POSITION_COLOR.INITIAL_CLIMB.value,
                mark=FLIGHT_PHASE.INITIAL_CLIMB.value,
                mark_tr=FLIGHT_PHASE.INITIAL_CLIMB.value,
            )
            currpos.setComment("initial climb (from airport)")

        if newidx == 0:
            logger.debug(f"moved flight plan index to 1")
            newidx = 1

        fcidx = newidx
        curralt = Altitude()
        curralt.in_ft = depapt_alt.in_ft + convert.meters_to_feet(INITIAL_CLIMB_SAFE_ALT_M)

        # ########################################################################################
        #
        # Version 1: New algorithm to climb from initial climb altitude to cruise altitude while respecting alt contraints.
        #            This only deals with altitude constraints, speed constraints will be adjusted after.
        #            There is no aircraft performance consideration.
        #
        # currpos is end of initial climb
        # from now on, curralt is MSL
        #
        if self.flight.procedures.get(FLIGHT_SEGMENT.SID.value) is not None:
            logger.debug(f"--------------- climbing with constraints..")
            logger.debug(f"SID = {self.flight.procedures.get(FLIGHT_SEGMENT.SID.value).name}")

            # Initial values, after initial climb
            curridx = fcidx  # we use curridx inside this if/then/else, we'll set fcidx back after this processing

            logger.debug(f"fcidx={fcidx}, curralt={curralt}")

            # Step 1: We are climbing... where is the next alt constraint we have to climb above?
            #
            # Note: this procedure just check for alt constraints.
            # Now is the aircraft capable of climing that fast? That is handled in climb_to_alt().
            # If not, climb_to_alt() will report a potential constraint violation.
            MAX_RESTRICTION_COUNT = 20
            LOOK_AHEAD_DISTANCE = 250  # km

            f = fpln[curridx]
            if hasattr(f, "hasRestriction") and f.hasRestriction():
                logger.debug(f"start index idx={curridx} has restriction, backing up to {max(curridx - 1, 0)}")
                curridx = max(curridx - 1, 0)

            logger.debug(f"getting next above restriction after idx={curridx} ({LOOK_AHEAD_DISTANCE}km)")
            r = self.flight.next_above_alt_restriction(curridx, max_distance=LOOK_AHEAD_DISTANCE)
            above_restrictions = 0
            while r is not None and above_restrictions < MAX_RESTRICTION_COUNT:
                above_restrictions = above_restrictions + 1
                restricted_above_alt = r.alt2 if r.alt_restriction_type in ["B"] else r.alt1
                logger.debug(f"at index {curridx} at alt {curralt}, next restriction above at idx={fpi(r)} {r.getRestrictionDesc()}")

                logger.debug(f"getting next below restriction between idx={curridx} and {fpi(r)}")
                r2 = self.flight.next_below_alt_restriction_idx(curridx, fpi(r))

                # Step 1b : While climbing there, are there any constraints we have to stay below?
                below_restrictions = 0
                while r2 is not None and below_restrictions < MAX_RESTRICTION_COUNT:
                    # r2.alt1 is "below" limit in all cases
                    below_restrictions = below_restrictions + 1
                    restricted_below_alt = r2.alt1
                    logger.debug(
                        f"at index {curridx} at alt {curralt}, next restriction below at idx={fpi(r2)} {r2.getRestrictionDesc()}, will climb at {restricted_below_alt}"
                    )
                    tidx = fpi(r2)
                    curridx, curralt.in_ft = climb_to_alt(
                        start_idx=curridx,
                        current_altitude=curralt.in_ft,
                        target_altitude=restricted_below_alt,
                        target_index=tidx,
                        comment="remain below restriction",
                    )
                    logger.debug(f"at index {curridx} at alt {curralt}, checking for next below restriction")

                    logger.debug(f"getting next below restriction between idx={fpi(r2)} and {fpi(r)}")
                    r2 = self.flight.next_below_alt_restriction_idx(fpi(r2), fpi(r))

                # Step 1c: Resume climbing to constraint to climb above...
                if curralt.in_ft < restricted_above_alt:
                    logger.debug(f"at index {curridx} at alt {curralt}, no more below restrictions, will climb to above restriction {restricted_above_alt}ft")
                    tidx = fpi(r)
                    curridx, curralt.in_ft = climb_to_alt(
                        start_idx=curridx,
                        current_altitude=curralt.in_ft,
                        target_altitude=restricted_above_alt,
                        target_index=tidx,
                        comment="climb above restriction",
                    )
                else:
                    logger.debug(f"at index {curridx} at alt {curralt}, no need to climb, already at or above restriction {restricted_above_alt}ft")
                    tidx = fpi(r)
                    curridx, curralt.in_ft = climb_to_alt(
                        start_idx=curridx,
                        current_altitude=curralt.in_ft,
                        target_altitude=restricted_above_alt,
                        target_index=tidx,
                        comment="climb above restriction",
                    )

                logger.debug(f"getting next above restriction after idx={fpi(r)} ({LOOK_AHEAD_DISTANCE}km)")
                r = self.flight.next_above_alt_restriction(fpi(r), max_distance=LOOK_AHEAD_DISTANCE)

            logger.debug(f"at index {curridx} at alt {curralt}, after {above_restrictions} above restrictions, NO MORE ABOVE RESTRICTION")

            # Step 2: No more constraints to climb above, but while climbing to cruise alt, are there any constraints we have to stay below?
            cruise_alt = Altitude()
            cruise_alt.in_ft = self.flight.flight_level * 100  # Target alt for climb, should actually be last alt for SID
            logger.debug(f"at index {curridx} at alt {curralt}, attempting to climb to cruise alt {cruise_alt.in_ft}ft, checking for below restrictions")
            idx_to_cruise_alt, dummy = climb_to_alt(
                start_idx=curridx, current_altitude=curralt.in_ft, target_altitude=cruise_alt.in_ft, target_index=None, do_it=False
            )

            logger.debug(f"getting next below restriction between idx={curridx} and {idx_to_cruise_alt}")
            r3 = self.flight.next_below_alt_restriction_idx(curridx, idx_to_cruise_alt)
            below_restrictions = 0
            while r3 is not None and below_restrictions < MAX_RESTRICTION_COUNT:
                below_restrictions = below_restrictions + 1
                restricted_below_alt = r3.alt1
                logger.debug(
                    f"at index {curridx} at alt {curralt}, next restriction below at {fpi(r3)} {r3.getRestrictionDesc()}, will climb at {restricted_below_alt}"
                )
                tidx = fpi(r3)
                curridx, curralt.in_ft = climb_to_alt(
                    start_idx=curridx,
                    current_altitude=curralt.in_ft,
                    target_altitude=restricted_below_alt,
                    target_index=tidx,
                    comment="remain below restriction",
                )
                # we now have to reevaluate when we will reach cruise alt...
                # curralt will temporarily be cruise alt, but if new r3 is not None, curralt will fall back to new restricted_below_alt
                logger.debug(f"getting next below restriction between idx={curridx} and {idx_to_cruise_alt}")
                r3 = self.flight.next_below_alt_restriction_idx(curridx, idx_to_cruise_alt)

            logger.debug(f"at index {curridx} at alt {curralt}, no more below restriction, will now climb to {cruise_alt} with no restriction")
            logger.debug(f"--------------- ..done climbing with constraints")

            if curralt.in_ft > 10000:
                logger.debug(f"note: restricted climb finishes above FL100")
            if curralt.in_ft > cruise_alt.in_ft:
                logger.warning(f"note: restricted climb finishes above cruise altitude")

            # "transition" :-) to former algorithm
            # Note: From previous algorithm, without contrains, rather than picking up from end of initial clim at 1500FT AGL,
            #       we are now at current alt a few indices later... nothing else differs.
            #       Resuming climb unconstrained to "cruise alt", from curralt rather than end_of_initial_climb.
            fcidx = curridx
            last_restricted_point = fpln[curridx]
            currpos = addMovepoint(
                arr=self._premoves,
                src=last_restricted_point,
                alt=curralt.in_m,
                speed=actype.low_alt_max_speed(alt=curralt.in_m, speed=actype.getSI(ACPERF.climbFL150_speed)),
                vspeed=actype.getSI(ACPERF.climbFL150_vspeed),
                color=POSITION_COLOR.CLIMB.value,
                mark=FLIGHT_PHASE.END_DEPARTURE_RESTRICTIONS.value,
                ix=fcidx,
            )
            currpos.setComment("last point of restricted climb")

            logger.debug(f"last point of restricted climb idx {curridx} at alt={self._premoves[-1].altitude()} (has {len(self._premoves)} premoves)")
            logger.debug(f"resume climb from {self._premoves[-1].altitude()} with no restriction to cruise altitude")
        else:
            logger.debug(f"no SID, no restriction, climb to cruise altitude according to aicraft capabilities")

        # ########################################################################################
        #
        # Version 2: Either continue climb to cruise altitude after SID (and restrictions) or after initial climb (if no SID)
        #
        # There might an issue if first point of SID is between TAKE_OFF and END_OF_INITIAL_CLIMB (which is about 4km from takeoff point).
        # It is very rare (buy it may happen, in which case the solution is to remove the first (few) point(s) of the SID)
        # Example of issue: BEY-DOH //DEP OLBA RW34 SID LEBO2F //ARR OTHH
        #
        if self._premoves[-1].altitude() < convert.feet_to_meters(10010):
            logger.debug("climbToFL100")
            step = actype.climbToFL100(currpos.altitude())  # (t, d, altend)
            groundmv = groundmv + step[1]
            currpos, fcidx = moveOnLS(
                coll=self._premoves,
                reverse=False,
                fc=fpln,
                fcidx=fcidx,
                currpos=currpos,
                dist=step[1],
                alt=step[2],
                speed=actype.low_alt_max_speed(alt=step[2], speed=actype.getSI(ACPERF.climbFL150_speed)),
                vspeed=actype.getSI(ACPERF.climbFL150_vspeed),
                color=POSITION_COLOR.CLIMB.value,
                mark="end_fl100_climb",
                mark_tr=FLIGHT_PHASE.CLIMB.value,
            )

        # climb to cruise altitude
        # added 10ft to alt in feet because of rounding would get alt < convert.feet_to_meters(15000)
        cruise_speed = actype.getSI(ACPERF.cruise_mach)

        if self._premoves[-1].altitude() <= convert.feet_to_meters(15010) and self.flight.flight_level > 150:
            logger.debug("climbToFL150")
            step = actype.climbToFL150(currpos.altitude())  # (t, d, altend)
            groundmv = groundmv + step[1]
            currpos, fcidx = moveOnLS(
                coll=self._premoves,
                reverse=False,
                fc=fpln,
                fcidx=fcidx,
                currpos=currpos,
                dist=step[1],
                alt=step[2],
                speed=actype.getSI(ACPERF.climbFL150_speed),
                vspeed=actype.getSI(ACPERF.climbFL150_vspeed),
                color=POSITION_COLOR.CLIMB.value,
                mark="end_fl150_climb",
                mark_tr=FLIGHT_PHASE.CLIMB.value,
            )

            if self._premoves[-1].altitude() <= convert.feet_to_meters(24010) and self.flight.flight_level > 240:
                logger.debug("climbToFL240")
                step = actype.climbToFL240(currpos.altitude())  # (t, d, altend)
                groundmv = groundmv + step[1]
                currpos, fcidx = moveOnLS(
                    coll=self._premoves,
                    reverse=False,
                    fc=fpln,
                    fcidx=fcidx,
                    currpos=currpos,
                    dist=step[1],
                    alt=step[2],
                    speed=actype.getSI(ACPERF.climbFL240_speed),
                    vspeed=actype.getSI(ACPERF.climbFL240_vspeed),
                    color=POSITION_COLOR.CLIMB.value,
                    mark="end_fl240_climb",
                    mark_tr=FLIGHT_PHASE.CLIMB.value + "1",
                )

                if self._premoves[-1].altitude() <= convert.feet_to_meters(24010) and self.flight.flight_level > 240:
                    logger.debug("climbToCruise")
                    step = actype.climbToCruise(currpos.altitude(), self.flight.getCruiseAltitude())  # (t, d, altend)
                    groundmv = groundmv + step[1]
                    currpos, fcidx = moveOnLS(
                        coll=self._premoves,
                        reverse=False,
                        fc=fpln,
                        fcidx=fcidx,
                        currpos=currpos,
                        dist=step[1],
                        alt=step[2],
                        speed=actype.getSI(ACPERF.climbmach_mach),
                        vspeed=actype.getSI(ACPERF.climbmach_vspeed),
                        color=POSITION_COLOR.TOP_OF_ASCENT.value,
                        mark=FLIGHT_PHASE.TOP_OF_ASCENT.value,
                        mark_tr=FLIGHT_PHASE.CLIMB.value,
                    )
                    # cruise speed defaults to ACPERF.cruise_mach, we don't need to specify it
            else:
                logger.debug("climbToCruise below FL240")
                step = actype.climbToCruise(currpos.altitude(), self.flight.getCruiseAltitude())  # (t, d, altend)
                groundmv = groundmv + step[1]
                currpos, fcidx = moveOnLS(
                    coll=self._premoves,
                    reverse=False,
                    fc=fpln,
                    fcidx=fcidx,
                    currpos=currpos,
                    dist=step[1],
                    alt=step[2],
                    speed=actype.getSI(ACPERF.climbFL240_speed),
                    vspeed=actype.getSI(ACPERF.climbFL240_vspeed),
                    color=POSITION_COLOR.TOP_OF_ASCENT.value,
                    mark=FLIGHT_PHASE.TOP_OF_ASCENT.value,
                    mark_tr=FLIGHT_PHASE.CLIMB.value,
                )
                cruise_speed = (actype.getSI(ACPERF.climbFL240_speed) + actype.getSI(ACPERF.cruise_mach)) / 2
                logger.warning(f"cruise speed below FL240: {cruise_speed:f} m/s")
        else:
            logger.debug("climbToCruise below FL150")
            step = actype.climbToCruise(currpos.altitude(), self.flight.getCruiseAltitude())  # (t, d, altend)
            groundmv = groundmv + step[1]
            currpos, fcidx = moveOnLS(
                coll=self._premoves,
                reverse=False,
                fc=fpln,
                fcidx=fcidx,
                currpos=currpos,
                dist=step[1],
                alt=step[2],
                speed=actype.getSI(ACPERF.climbFL240_speed),
                vspeed=actype.getSI(ACPERF.climbFL240_vspeed),
                color=POSITION_COLOR.TOP_OF_ASCENT.value,
                mark=FLIGHT_PHASE.TOP_OF_ASCENT.value,
                mark_tr=FLIGHT_PHASE.CLIMB.value,
            )
            logger.warning(f"cruise speed below FL150: {cruise_speed:f} m/s")
            cruise_speed = (actype.getSI(ACPERF.climbFL150_speed) + actype.getSI(ACPERF.cruise_mach)) / 2

        # accelerate to cruise speed smoothly
        ACCELERATION_DISTANCE = 5000  # we reach cruise speed after 5km horizontal flight
        logger.debug("accelerate to cruise speed")
        currpos, fcidx = moveOnLS(
            coll=self._premoves,
            reverse=False,
            fc=fpln,
            fcidx=fcidx,
            currpos=currpos,
            dist=ACCELERATION_DISTANCE,
            alt=step[2],
            speed=cruise_speed,
            vspeed=0,
            color=POSITION_COLOR.ACCELERATE.value,
            mark="reached_cruise_speed",
            mark_tr=FLIGHT_PHASE.ACCELERATE.value,
        )

        top_of_ascent_idx = fcidx + 1  # we reach top of ascent between idx and idx+1, so we cruise from idx+1 on.
        logger.debug("cruise at %d after %f" % (top_of_ascent_idx, round(groundmv, 2)))
        logger.debug(f"ascent added (+{len(self._premoves)} {len(self._premoves)})")
        #
        #
        # CRUISE ALTITUDE REACHED
        # Cruise will be added later.
        #
        # ########################################################################################
        #
        # PART 2: DESCEND TO ROLL OUT
        #
        # PART 2.1: In reverse order, from ROLL OUT back to FINAL FIX
        #
        logger.debug(f"arrival to {self.flight.arrival.icao} " + "=" * 30)

        # Set a few default sensible values in case procedures do not give any
        #
        # STAR
        #
        star_alt = Altitude()
        star_alt.in_ft = 6000
        starproc = self.flight.procedures.get(FLIGHT_SEGMENT.STAR.value)
        if starproc is not None:
            dummy, star_alt.in_ft = starproc.getEntrySpeedAndAlt()  # returns sensible default if none found

        # APPROACH
        #
        approach_alt = Altitude()
        approach_alt.in_ft = 3000  # Altitude ABG at which we perform approach path before final
        # approach_alt.in_ft = int(approach_alt.in_ft)

        # FINAL
        #
        # FIX
        final_fix_alt = Altitude()
        final_fix_alt.in_ft = Altitude.NO_ALTITUDE_VALUE  # Altitude ABG at which we start final, always straight line aligned with runway

        # 1. Try to get defaults from procedure
        apchproc = self.flight.procedures.get(FLIGHT_SEGMENT.APPCH.value)
        if apchproc is not None:
            if final_fix_alt.in_ft == Altitude.NO_ALTITUDE_VALUE:
                final_fix_alt.in_ft = apchproc.getFinalFixAltInFt(default=Altitude.NO_ALTITUDE_VALUE)
                if final_fix_alt.in_ft is None:
                    logger.debug("no final fix altitude")

        if final_fix_alt.in_ft == Altitude.NO_ALTITUDE_VALUE:
            final_fix_alt.in_m = FINAL_APPROACH_FIX_ALT_M
            logger.debug(f"using default final fix altitude {final_fix_alt}")

        final_fix_alt.in_ft = int(final_fix_alt.in_ft)
        logger.debug(f"final fix alt {final_fix_alt} (AGL)")

        # VSPEED
        final_vspeed = VSpeed(0)
        final_vspeed.in_fpm = 0

        if final_vspeed.in_fpm == 0:
            if actype.getSI(ACPERF.landing_speed) is not None and actype.getSI(ACPERF.landing_speed) > 0:
                # Alternative 2 : VSPEED adjusted to have an angle/ratio of 3% (common)
                # Note: Landing speed is in kn. 1 kn = 101.26859 ft/min :-)
                landing_speed_kn = actype.get(ACPERF.landing_speed)
                final_vspeed.in_fpm = 0.03 * landing_speed_kn * 101.26859
                logger.debug(f"final vspeed from 3% landing speed (={landing_speed_kn}kn)")

        if final_vspeed.in_fpm == 0:
            final_vspeed.in_fpm = 600
            logger.debug(f"final vspeed from default")

        logger.debug(f"final vspeed {final_vspeed}")

        #
        # Create (reverse) path
        # ROLLOUT + TOUCH DOWN + LANDING + FINAL APPROACH from final fix
        #
        LAND_TOUCH_DOWN = 0.4  # km, distance of touch down from the runway threshold (given in CIFP)

        revmoves = []
        groundmv = 0
        fplnrev = fpln.copy()
        fplnrev.reverse()
        fplnidx_rev = 0
        last_rev_idx = len(fplnrev) - 1
        artificial_final_fix = None

        is_grounded = True

        rwy = None
        if self.flight.is_arrival():  # we are at the managed airport, we must use the selected runway
            rwy = self.flight.rwy
        else:
            rwy = self.flight.arrival.selectRWY(self.flight)
            logger.debug(f"remote arrival: using runway {rwy.name}")

        if rwy is not None:  # the path starts at the of roll out
            rwy_threshold = rwy.getPoint()
            alt = rwy_threshold.altitude()
            if alt is None:
                logger.warning(f"(rev) departure airport has no altitude: {rwy_threshold}")
                arrapt_alt.in_m = 0
            else:
                arrapt_alt.in_m = float(alt)
                logger.debug(f"arrival airport at altitude {round(arrapt_alt.in_m,1)}m")

            brg = bearing(rwy_threshold, rwy.end.getPoint())
            touch_down = destination(rwy_threshold, LAND_TOUCH_DOWN, brg)
            logger.debug(f"(rev) arrival runway {rwy.name}, {brg:f}")

            # First point is end off roll out, read to exit the runway and taxi
            rollout_distance = actype.getSI(ACPERF.landing_distance) * self.airport.runwayIsWet() / 1000  # must be km for destination()
            end_rollout = destination(touch_down, rollout_distance, brg)

            currpos = addMovepoint(
                arr=revmoves,
                src=end_rollout,
                alt=arrapt_alt.in_m,
                speed=TAXI_SPEED,
                vspeed=0,
                color=POSITION_COLOR.ROLL_OUT.value,
                mark=FLIGHT_PHASE.END_ROLLOUT.value,
                ix=last_rev_idx - fplnidx_rev,
            )
            logger.debug(f"(rev) end roll out at {rwy.name}, landing distance={rollout_distance:f}km, alt={round(arrapt_alt.in_m,1)}")
            self.end_rollout = copy.deepcopy(currpos)  # we keep this special position for taxiing (start_of_taxi)

            # Point just before is touch down
            p = addMovepoint(
                arr=revmoves,
                src=touch_down,
                alt=arrapt_alt.in_m,
                speed=actype.getSI(ACPERF.landing_speed),
                vspeed=0,
                color=POSITION_COLOR.TOUCH_DOWN.value,
                mark=FLIGHT_PHASE.TOUCH_DOWN.value,
                ix=last_rev_idx - fplnidx_rev,
            )
            logger.debug(f"(rev) touch down at {rwy.name}, distance from threshold={LAND_TOUCH_DOWN:f}km, alt={round(arrapt_alt.in_m,1)}")

            self.addMessage(
                FlightMessage(
                    subject=f"ACARS: {ac.icao24} {FLIGHT_PHASE.TOUCH_DOWN.value} at {self.flight.arrival.icao}",
                    flight=self,
                    sync=FLIGHT_PHASE.TOUCH_DOWN.value,
                    info=self.getInfo(),
                )
            )
            is_grounded = False

            # we move to the final fix at max final_fix_alt.in_ft ft, landing speed, final_vspeed.in_fpm (ft/min), from touchdown
            logger.debug("(rev) final")
            step = actype.descentFinal(arrapt_alt.in_m, final_vspeed.in_ms, safealt=final_fix_alt.in_m)  # (t, d, altend)
            final_distance = step[1] / 1000  # km
            # find final fix point

            # we (reverse) descent on path to see if we reach indices...
            p, newidx = moveOn(fplnrev, fplnidx_rev, p, final_distance)

            # we ignore currpos for now, we will descent straight, we ignore points
            # between fplnidx_rev and newidx during final descent...
            artificial_final_fix = destination(touch_down, final_distance, brg + 180)

            currpos = addMovepoint(
                arr=revmoves,
                src=artificial_final_fix,
                alt=arrapt_alt.in_m + final_fix_alt.in_m,
                speed=actype.getSI(ACPERF.landing_speed),
                vspeed=final_vspeed.in_ms,
                color=POSITION_COLOR.FINAL.value,
                mark=FLIGHT_PHASE.FINAL_FIX.value,
                ix=last_rev_idx - fplnidx_rev,
            )
            logger.debug(
                ", ".join(
                    [
                        f"(rev) final fix at new idx={newidx}(old idx={fplnidx_rev})",
                        f"distance from touch-down={final_distance}km",
                        f"alt={arrapt_alt} + {final_fix_alt}",
                        f"(v/s={final_vspeed}",
                        f"speed={actype.getSI(ACPERF.landing_speed)}m/s,{actype.get(ACPERF.landing_speed)}kn)",
                    ]
                )
            )
            groundmv = groundmv + final_distance
            #
            # Possible issue: we ignore vertices between final fix and touch down
            # we go in straight line and ignore self._premoves, skipping eventual points
            #
            fplnidx_rev = newidx

        else:  # no run way
            arrvapt = fplnrev[fplnidx_rev]
            alt = arrvapt.altitude()
            if alt is None:
                logger.warning(f"(rev) arrival airport has no altitude: {arrvapt}")
                arrapt_alt.in_m = 0
            else:
                arrapt_alt.in_m = float(alt)

            currpos = addMovepoint(
                arr=revmoves,
                src=arrvapt,
                alt=arrapt_alt.in_m,
                speed=actype.getSI(ACPERF.landing_speed),
                vspeed=final_vspeed.in_ms,
                color=POSITION_COLOR.DESTINATION.value,
                mark="destination",
                ix=len(fplnrev) - fplnidx_rev,
            )
            logger.debug("(rev) destination added as last point")

            self.addMessage(
                FlightMessage(
                    subject=f"ACARS: {ac.icao24} {FLIGHT_PHASE.TOUCH_DOWN.value} at {self.flight.arrival.icao}",
                    flight=self,
                    sync=FLIGHT_PHASE.TOUCH_DOWN.value,
                    info=self.getInfo(),
                )
            )
            is_grounded = False

            # we move to the final fix at max 3000ft, approach speed from airport last point, vspeed=final_vspeed.in_fpm
            logger.debug("(rev) final")
            step = actype.descentFinal(arrapt_alt.in_m, final_vspeed.in_ms, safealt=final_fix_alt.in_ft)  # (t, d, altend)
            groundmv = groundmv + step[1]
            # find final fix point
            currpos, fplnidx_rev = moveOnLS(
                coll=revmoves,
                reverse=True,
                fc=fplnrev,
                fcidx=fplnidx_rev,
                currpos=currpos,
                dist=step[1],
                alt=arrapt_alt.in_m + final_fix_alt.in_m,
                speed=actype.getSI(ACPERF.landing_speed),
                vspeed=final_vspeed.in_ms,
                color=POSITION_COLOR.FINAL.value,
                mark=FLIGHT_PHASE.FINAL_FIX.value,
                mark_tr=FLIGHT_PHASE.FINAL.value,
            )
            artificial_final_fix = currpos  # in this case, final fix is a point on the slope from before last flight plan point to airport.

        # We now have a reverse path from final fix alt to either touchdown to rollout or to airport center (if no rwy).
        # Final fix to touch down is (vspeed=)600ft/min at (speed=)landing speed.
        #
        # ########################################################################################
        #
        # PART 2.2: DESCEND FROM CRUISE TO FINAL FIX
        # Version 1: Using procedures, going forward from TOD to final fix
        #            New algorithm to descend from cruise altitude to final fix while respecting alt contraints.
        #            In this algorithm, cruise is added as soon as TOD is found. cruise_add is then True.
        #
        cruise_added = False
        cruise_alt = Altitude()
        if self.flight.procedures.get(FLIGHT_SEGMENT.STAR.value) is not None or self.flight.procedures.get(FLIGHT_SEGMENT.APPCH.value):
            logger.debug(f"--------------- descending with constraints..")
            if self.flight.procedures.get(FLIGHT_SEGMENT.STAR.value) is not None:
                logger.debug(f"STAR = {self.flight.procedures.get(FLIGHT_SEGMENT.STAR.value).name}")
            if self.flight.procedures.get(FLIGHT_SEGMENT.APPCH.value) is not None:
                appch = self.flight.procedures.get(FLIGHT_SEGMENT.APPCH.value)
                logger.debug(f"APPCH = {appch.name}")

            logger.debug(f"(artificial) final fix alt {final_fix_alt}")
            cruise_start_idx, cruise_end_idx = self.flight.phase_indices(phase=FLIGHT_SEGMENT.CRUISE)
            cruise_start_idx = max(cruise_start_idx, top_of_ascent_idx)  # if no start procedure, climbed from departure airport
            cruise_alt.in_ft = self.flight.flight_level * 100

            # Start situation before descend
            #
            # Note: We may start descend before this end of cruise.
            #
            # curridx is the index in the flight plan
            # curralt is the current altitude at the same stage as curridx
            #
            curridx = cruise_end_idx
            curralt.in_ft = cruise_alt.in_ft
            if curridx is None:
                logger.debug(f"cannot find end of cruise")
            else:
                logger.debug(f"cruise finishes at {curridx} at {curralt}")

            # last point of descend
            #
            last_pt_fpln_index = len(fpln) - 2  # not correct
            last_pt_fpln_alt = Altitude()
            d = distance(fpln[len(fpln) - 2], fpln[len(fpln) - 1])
            logger.debug(f"last point in flight plan index {last_pt_fpln_index} at {round(d,1)}km from runway")
            if fpln[last_pt_fpln_index].hasAltitudeRestriction():
                last_alt = fpln[last_pt_fpln_index].getLowestAlt()
                if last_alt is not None or last_alt > last_pt_fpln_alt.in_ft:
                    last_pt_fpln_alt.in_ft = last_alt
                    logger.debug(f"has restriction {fpln[last_pt_fpln_index].getRestrictionDesc()}")
                else:
                    last_pt_fpln_alt.in_m = FINAL_APPROACH_FIX_ALT_M
                    logger.debug(f"has restriction {fpln[last_pt_fpln_index].getRestrictionDesc()} but no altitude found, using default")
            else:  # last point has no restriction, we add ours. it fails if last point too far from runway...
                r = Restriction(
                    altmin=convert.meters_to_feet(FINAL_APPROACH_FIX_ALT_M), speed=actype.get(ACPERF.landing_speed)
                )  # in imperial units for restriction
                r.alt_restriction_type = "@"
                r.speed_restriction_type = "@"
                fpln[last_pt_fpln_index].add_restriction(r)
                last_pt_fpln_alt.in_m = FINAL_APPROACH_FIX_ALT_M
                logger.debug(f"had no restriction, added artificial restriction {r.getRestrictionDesc()}")

            logger.debug(f"last point of flight plan at index {last_pt_fpln_index} at alt {last_pt_fpln_alt}")

            # Step 1: While descending, are there restriction we have to fly below (i.e. expedite descend)
            MAX_RESTRICTION_COUNT = 20
            LOOK_AHEAD_DISTANCE = 250  # km

            logger.debug(f"getting next below restriction after idx={curridx} ({LOOK_AHEAD_DISTANCE}km)")
            r = self.flight.next_below_alt_restriction(curridx, max_distance=LOOK_AHEAD_DISTANCE)  # km

            below_restrictions = 0
            while r is not None and below_restrictions < MAX_RESTRICTION_COUNT:
                below_restrictions = below_restrictions + 1
                logger.debug(f"\n\n>>>>>>>>>> at index {curridx} at alt {curralt}, doing next restriction below at idx={fpi(r)} {r.getRestrictionDesc()}..")

                # when should we start to descend to satisfy this? current_altitude, target_index, target_altitude
                candidate_alt = r.alt1
                start_idx = curridx
                if curralt.in_ft > candidate_alt:
                    min_idx = curridx
                    if not has_top_of_descend:  # we can backup to the start of cruise! to start our descend
                        min_idx = cruise_start_idx
                    start_idx = get_descend_start_index(min_index=min_idx, current_altitude=curralt.in_ft, target_index=fpi(r), target_altitude=candidate_alt)
                    logger.debug(
                        f"must start descend from {curralt.in_ft} at {start_idx} to satisfy restriction below at idx={fpi(r)} {r.getRestrictionDesc()}"
                    )
                    if start_idx < cruise_start_idx:
                        logger.warning(
                            f"cruise start at {cruise_start_idx} and descend should start at {start_idx}, please lower cruise flight level (current is {self.flight.flight_level})"
                        )
                else:
                    logger.debug(f"at index {curridx} at alt {curralt}, below restriction {r.getRestrictionDesc()} already satified")
                    # we were just *checking*, we do not move to the cleared restriction

                if not cruise_added:
                    if curralt.in_ft != cruise_alt.in_ft:
                        logger.warning(f"not at cruise altitude any more? current alt={curralt}, cruise alt={cruise_alt.in_ft}")
                    logger.debug(f"adding cruise (with below restrictions): from {cruise_start_idx} to {start_idx}")
                    add_cruise(cruise_start_idx, min(cruise_end_idx, start_idx))
                    curridx = min(cruise_end_idx, start_idx)
                    cruise_added = True
                # we are now at start of descend at curridx, still at curralt=cruise_alt.
                # we know we can descend at reasonable rate to next restricted altitude.

                # Step 1b: While descending there, are there restrictions we have to stay above (i.e. not descend too fast...)
                logger.debug(f"getting next above restriction between {curridx} and {fpi(r)}")
                r2 = self.flight.next_above_alt_restriction_idx(curridx, fpi(r))

                above_restrictions = 0
                while r2 is not None and above_restrictions < MAX_RESTRICTION_COUNT:
                    logger.debug(f">>>>> doing above restriction {r2.getRestrictionDesc()} at {fpi(r2)}..")
                    above_restrictions = above_restrictions + 1
                    restricted_above_alt = r2.alt2 if r2.alt_restriction_type in ["B"] else r2.alt1
                    if fpi(r) == fpi(r2):
                        logger.debug(f"same waypoint")
                        if curralt.in_ft < restricted_above_alt:
                            logger.warning(f"cannot satisfy restrictions at {curridx} {r2.getRestrictionDesc()}")
                    else:
                        # If we descend according to above below restriction plans, what would our altitude at idx fpi(r2) be?
                        my_alt_at_r2 = altitude_at_index(fpi(r2), start_idx=curridx, start_alt=curralt.in_ft, end_idx=fpi(r), end_alt=r.alt1)
                        if my_alt_at_r2 != -1 and restricted_above_alt > my_alt_at_r2:
                            # we have to slow down our descend to remain above a restriction
                            logger.debug(
                                ", ".join(
                                    [
                                        f"above restriction {r2.getRestrictionDesc()} at {fpi(r2)} NOT cleared (at {round(my_alt_at_r2,0)}ft)",
                                        f"will do shallow descend to {restricted_above_alt} to comply",
                                    ]
                                )
                            )
                            tidx = fpi(r2)
                            curridx, curralt.in_ft = descend_to_alt(
                                current_index=curridx,
                                current_altitude=curralt.in_ft,
                                target_altitude=restricted_above_alt,
                                target_index=tidx,
                                comment="descent to restricted above alt",
                            )
                            last_pt_fpln_alt.in_ft = min(last_pt_fpln_alt.in_ft, curralt.in_ft)
                            last_pt_fpln_alt_m = convert.feet_to_meters(last_pt_fpln_alt.in_ft)  # Default target alt for descend ft
                            logger.debug(f"above restriction {r2.getRestrictionDesc()} at {fpi(r2)} cleared (at {round(my_alt_at_r2,0)}ft)")
                            logger.debug(f"now at {curridx} at {curralt}")
                        else:
                            # we can ignore the above restriction, we will be above anyway
                            logger.debug(
                                f"above restriction {r2.getRestrictionDesc()} at {fpi(r2)} cleared at {round(my_alt_at_r2,0)}ft, no need to adjust descend"
                            )
                            logger.debug(f"now at {fpi(r2)} at {my_alt_at_r2}ft to clear restriction")

                    fpi_r2 = fpi(r2)
                    fpi_r = fpi(r)
                    logger.debug(f"<<<<< ..done above restriction {r2.getRestrictionDesc()} at {fpi(r2)}")

                    if fpi_r2 < fpi_r:
                        logger.debug(f"getting next above restriction between {fpi_r2} and {fpi_r}")
                        r2 = self.flight.next_above_alt_restriction_idx(fpi_r2, fpi_r)  # after this one, before the below restriction
                        # print("got above", fpi_r2, fpi_r, r2)
                    else:
                        logger.debug(f"at below restriction {r.getRestrictionDesc()} at {fpi_r}")
                        r2 = None

                logger.debug(
                    f"at index {curridx} at alt {curralt}, no more above restriction before idx {fpi(r)} with below restriction {r.getRestrictionDesc()}"
                )

                # Step 1c: no more above restrictions we descend to satify Step 1
                if candidate_alt < curralt.in_ft:
                    tidx = fpi(r)
                    logger.debug(f"at index {curridx} at alt {curralt}, no more above restrictions, will decend to {candidate_alt} at {tidx}")
                    curridx, curralt.in_ft = descend_to_alt(
                        current_index=curridx,
                        current_altitude=curralt.in_ft,
                        target_altitude=r.alt1,
                        target_index=tidx,
                        comment="descend to at or below restricted altitude",
                    )
                    last_pt_fpln_alt.in_ft = min(last_pt_fpln_alt.in_ft, curralt.in_ft)
                    last_pt_fpln_alt_m = convert.feet_to_meters(last_pt_fpln_alt.in_ft)  # Default target alt for descend ft
                else:
                    logger.debug(f"at index {curridx} at alt {curralt}, already below or at below restriction {candidate_alt}ft, no need to descend")
                    # MUST ADD CURRENT POINT TO _PREMOVES (at or below restricted alt)
                    logger.debug(f"must add current satified point")
                    tidx = fpi(r)
                    curridx, curralt.in_ft = descend_to_alt(
                        current_index=curridx,
                        current_altitude=curralt.in_ft,
                        target_altitude=r.alt1,
                        target_index=tidx,
                        comment="already below or at below restriction",
                    )
                    logger.debug(f"at index {fpi(r)} at alt {curralt}, already below or at below restriction {candidate_alt}ft, no need to descend")

                logger.debug(f"at index {curridx} at alt {curralt}")
                logger.debug(f"<<<<<<<<<< ..done below restriction {r.getRestrictionDesc()} at {fpi(r)}\n\n")
                # assert currind >= rpi(r)
                fpi_r = fpi(r)
                logger.debug(f"getting next below restriction after idx={fpi_r} ({LOOK_AHEAD_DISTANCE}km)")
                r = self.flight.next_below_alt_restriction(fpi_r, max_distance=LOOK_AHEAD_DISTANCE)  # km
                # print("got below", fpi_r, r)

            logger.debug(f"at index {curridx} at alt {curralt}, after {below_restrictions} below restriction, NO MORE BELOW RESTRICTION")
            logger.debug(
                f"at index {curridx} at alt {curralt}, attempting to descend to final fix alt {last_pt_fpln_alt.in_ft}ft, checking for above restrictions"
            )

            # So far, cleared all at or "below" restrictions, while keeping the aircraft above "above" restrictions in between.
            # We are now left with remaining of descend to last_pt_fpln_alt.in_ft but we have to remain above potential above restrictions
            # in our path

            # ISSUE when before last point in fpln has restriction.
            # Need to insert artificial final fix before landing...

            if curridx < last_pt_fpln_index:  # we are not yet at the final fix
                logger.debug(f"there was {below_restrictions} below restriction(s)")
                logger.debug(f"must descend from {curralt.in_ft} at {curridx} to reach {last_pt_fpln_alt} at idx={last_pt_fpln_index}")
                if not cruise_added:
                    logger.debug(f"cruise not added before, may start descend before {curridx}..")
                    if curralt.in_ft != cruise_alt.in_ft:
                        logger.warning(f"not at cruise altitude any more? current alt={curralt.in_ft}, cruise alt={cruise_alt.in_ft}")
                    min_idx = curridx
                    if not has_top_of_descend:  # we can backup to the start of cruise! to start our descend
                        min_idx = cruise_start_idx
                    start_idx = get_descend_start_index(
                        min_index=min_idx, current_altitude=curralt.in_ft, target_index=last_pt_fpln_index, target_altitude=last_pt_fpln_alt.in_ft
                    )
                    real_end_cruise = min(cruise_end_idx, start_idx)
                    logger.debug(f"adding cruise (without below restrictions): from {cruise_start_idx} to {real_end_cruise}")
                    add_cruise(cruise_start_idx, real_end_cruise)
                    cruise_added = True
                    curridx = real_end_cruise

                    logger.debug(f"cruise added, must descend from {curralt.in_ft} at {curridx} to reach {last_pt_fpln_alt} at idx={last_pt_fpln_index}")

                # Now need to descend from curridx, curralt to last_pt_fpln_index, last_pt_fpln_alt.in_ft respecting above restrictions
                logger.debug(f"getting next above restriction between {curridx} and {last_pt_fpln_index}")
                r3 = self.flight.next_above_alt_restriction_idx(curridx, last_pt_fpln_index)
                above_restrictions = 0
                while r3 is not None and above_restrictions < MAX_RESTRICTION_COUNT:
                    logger.debug(f"===>> doing above restriction {r3.getRestrictionDesc()} at {fpi(r3)}..")
                    above_restrictions = above_restrictions + 1
                    restricted_above_alt = r3.alt2 if r3.alt_restriction_type in ["B"] else r3.alt1
                    # If we descend according to above below restriction plans, what would our altitude at idx fpi(r2) be?
                    my_alt_at_r3 = altitude_at_index(
                        fpi(r3), start_idx=curridx, start_alt=curralt.in_ft, end_idx=last_pt_fpln_index, end_alt=last_pt_fpln_alt.in_ft
                    )
                    # if my_alt_at_r3 != -1:
                    #     addMovepoint()
                    #     curridx = last_pt_fpln_index
                    # elif my_alt_at_r3 < restricted_above_alt:
                    if my_alt_at_r3 != -1 and my_alt_at_r3 < restricted_above_alt:
                        logger.debug(
                            ", ".join(
                                [
                                    f"above restriction {r3.getRestrictionDesc()} at {fpi(r3)} NOT cleared (at {round(my_alt_at_r3,0)}ft)",
                                    f"will do shallow descend to {restricted_above_alt} to comply",
                                ]
                            )
                        )
                        tidx = fpi(r3)
                        curridx, curralt.in_ft = descend_to_alt(
                            current_index=curridx,
                            current_altitude=curralt.in_ft,
                            target_altitude=restricted_above_alt,
                            target_index=tidx,
                            comment="descend to restricted above alt (after all below alt)",
                        )
                        last_pt_fpln_alt.in_ft = min(last_pt_fpln_alt.in_ft, curralt.in_ft)
                        last_pt_fpln_alt_m = convert.feet_to_meters(last_pt_fpln_alt.in_ft)  # Default target alt for descend ft
                        logger.debug(f"at index {curridx} at alt {curralt}")
                    else:
                        # we can ignore the above restriction, we will be above anyway
                        logger.debug(f"above restriction {r3.getRestrictionDesc()} at {fpi(r3)} cleared (at {round(my_alt_at_r3,0)}ft)")
                        logger.debug(f"at index {fpi(r3)} at alt {my_alt_at_r3}ft to clear restriction")

                    # we now have to reevaluate when we will reach final fix alt...
                    # curralt will temporarily be final fix alt, but if new r3 is not None, curralt will fall back to new r3.alt1
                    # idx_to_last_pt_fpln_alt2 = get_descend_start_index(
                    #     min_index=curridx, current_altitude=curralt, target_altitude=last_pt_fpln_alt_m, target_index=last_pt_fpln_index
                    # )
                    # logger.debug(f"index of final fix re-evaluated at {idx_to_last_pt_fpln_alt2}")

                    logger.debug(f"===<< ..done above restriction {r3.getRestrictionDesc()} at {fpi(r3)}")

                    # should be: logger.debug(f"getting next above restriction between {idx_to_last_pt_fpln_alt2} and {last_pt_fpln_index}")
                    if fpi(r3) < last_pt_fpln_index:
                        logger.debug(f"getting next above restriction between {fpi(r3)} and {last_pt_fpln_index}")
                        r3 = self.flight.next_above_alt_restriction_idx(fpi(r3), last_pt_fpln_index)
                    else:
                        logger.debug(f"at or after final fix index {last_pt_fpln_index}, no more above restrition before final fix")
                        r3 = None

                logger.debug(f"at index {curridx} at alt {curralt}")
                # descend from last above restriction, if any to final fix
                if curralt.in_ft > last_pt_fpln_alt.in_ft:
                    logger.debug(f"there was {above_restrictions} above restriction(s) since last below restriction")
                    logger.debug(
                        f"=== at index {curridx} at altitude {curralt.in_ft}, no more above restrictions, will descend to {last_pt_fpln_alt} with no restriction"
                    )
                    curridx, curralt.in_ft = descend_to_alt(
                        current_index=curridx,
                        current_altitude=curralt.in_ft,
                        target_altitude=last_pt_fpln_alt.in_ft,
                        target_index=last_pt_fpln_index,
                        comment="unconstrained final descend",
                    )
                    last_pt_fpln_alt.in_ft = min(last_pt_fpln_alt.in_ft, curralt.in_ft)
                    last_pt_fpln_alt_m = convert.feet_to_meters(last_pt_fpln_alt.in_ft)  # Default target alt for descend ft
                    logger.debug(f"at index {curridx} at alt {curralt}")
                else:
                    # we move to the final fix
                    curridx = last_pt_fpln_index
            else:
                logger.debug(f"at index {curridx} at alt {curralt}, at final fix or after")

            logger.debug(f"--------------- ..done descending with constraints")
            logger.debug(f"at index {curridx} at alt {curralt}, resume descend with no restriction to artificial final fix and to touch down")
            if curralt.in_ft > last_pt_fpln_alt.in_ft:
                logger.debug(f"note: restricted descend finishes above last point target altitude {last_pt_fpln_alt} (current {curralt})")

            logger.debug("adding end of descend..")
            revmoves.reverse()
            logger.debug(f"end of descend has {len(revmoves)} points")
            self._premoves = self._premoves + revmoves
            logger.debug("..added")
        else:
            logger.debug(f"no STAR and no APPROACH, no restriction, descend from cruise altitude to final fix according to aicraft capabilities")
        #
        #
        # PART 2.2: DESCEND FROM CRUISE TO FINAL FIX
        # Version 2: Not using procedures but straight descending segments following flight plan
        #            Version 2 is also used if version 1 failed
        #            Coded in reverse path: (climbing!) from final fix to cruise altitude.
        #
        # ########################################################################################
        #
        if not (
            cruise_added
            or self.flight.procedures.get(FLIGHT_SEGMENT.STAR.value) is not None
            or self.flight.procedures.get(FLIGHT_SEGMENT.APPCH.value) is not None
        ):
            logger.debug("(rev) vnav without restriction *****************")
            k = last_rev_idx
            while fplnrev[k].getProp(FEATPROP.PLAN_SEGMENT_TYPE) != "appch" and k > 0:
                k = k - 1
            if k == 0:
                logger.warning("no approach found")
            else:
                logger.debug("(rev) start of approach at index %d, %s" % (k, fplnrev[k].getProp(FEATPROP.PLAN_SEGMENT_TYPE)))
                if k <= fplnidx_rev:
                    logger.debug("(rev) final fix seems further away than start of apprach")
                else:
                    logger.debug("(rev) flight level to final fix")
                    # add all approach points between start to approach to final fix
                    first = True  # we name last point of approach "initial fix"
                    for i in range(fplnidx_rev + 1, k):
                        wpt = fplnrev[i]
                        # logger.debug("APPCH: flight level: %d %s" % (i, wpt.getProp(FEATPROP.PLAN_SEGMENT_TYPE)))
                        p = addMovepoint(
                            arr=revmoves,
                            src=wpt,
                            alt=arrapt_alt.in_m + approach_alt.in_m,
                            speed=actype.getSI(ACPERF.approach_speed),
                            vspeed=0,
                            color=POSITION_COLOR.APPROACH.value,
                            mark=(FLIGHT_PHASE.INITIAL_FIX.value if first else FLIGHT_PHASE.APPROACH.value),
                            ix=len(fplnrev) - i,
                        )
                        first = False
                        # logger.debug("adding remarkable point: %d %s (%d)" % (i, p.getProp(FEATPROP.MARK), len(revmoves)))

                    # add start of approach
                    currpos = addMovepoint(
                        arr=revmoves,
                        src=fplnrev[k],
                        alt=arrapt_alt.in_m + approach_alt.in_m,
                        speed=actype.getSI(ACPERF.approach_speed),
                        vspeed=0,
                        color=POSITION_COLOR.APPROACH.value,
                        mark="start_of_approach",
                        ix=len(fplnrev) - k,
                    )
                    # logger.debug("adding remarkable point: %d %s (%d)" % (k, currpos.getProp(FEATPROP.MARK), len(revmoves)))

                    fplnidx_rev = k

            # find first point of star:
            k = last_rev_idx
            while fplnrev[k].getProp(FEATPROP.PLAN_SEGMENT_TYPE) != "star" and k > 0:
                k = k - 1
            if k == 0:
                logger.warning("(rev) no star found")
            else:
                logger.debug("(rev) start of star at index %d, %s" % (k, fplnrev[k].getProp(FEATPROP.PLAN_SEGMENT_TYPE)))
                if k <= fplnidx_rev:
                    logger.debug("(rev) final fix seems further away than start of star")
                else:
                    logger.debug("(rev) flight level to start of approach")
                    # add all approach points between start to approach to final fix
                    for i in range(fplnidx_rev + 1, k):
                        wpt = fplnrev[i]
                        # logger.debug("STAR: flight level: %d %s" % (i, wpt.getProp(FEATPROP.PLAN_SEGMENT_TYPE)))
                        p = addMovepoint(
                            arr=revmoves,
                            src=wpt,
                            alt=arrapt_alt.in_m + star_alt.in_m,
                            speed=actype.getSI(ACPERF.approach_speed),
                            vspeed=0,
                            color=POSITION_COLOR.APPROACH.value,
                            mark="star",
                            ix=len(fplnrev) - i,
                        )

                        # logger.debug("adding remarkable point: %d %s (%d)" % (i, p.getProp(FEATPROP.MARK), len(revmoves)))
                    # add start of approach
                    currpos = addMovepoint(
                        arr=revmoves,
                        src=fplnrev[k],
                        alt=arrapt_alt.in_m + star_alt.in_m,
                        speed=actype.getSI(ACPERF.approach_speed),
                        vspeed=0,
                        color=POSITION_COLOR.APPROACH.value,
                        mark="start_of_star",
                        ix=len(fplnrev) - k,
                    )
                    # logger.debug("adding remarkable point: %d %s (%d)" % (k, currpos.getProp(FEATPROP.MARK), len(revmoves)))
                    #
                    # @todo: We assume start of star is where holding occurs
                    self.holdingpoint = fplnrev[k].id
                    # logger.debug("searching for holding fix at %s" % (self.holdingpoint))
                    # holds = self.airport.airspace.findHolds(self.holdingpoint)
                    # if len(holds) > 0:
                    #     holding = holds[0]  # keep fist one
                    #     logger.debug("found holding fix at %s (%d found), adding pattern.." % (holding.fix.id, len(holds)))
                    #     hold_pts = holding.getRoute(actype.getSI(ACPERF.approach_speed))
                    #     # !!! since the pattern is added to revmoves (which is reversed!)
                    #     # we need to reverse the pattern before adding it.
                    #     # it will be inversed again (back to its original sequence)
                    #     # at revmoves.reverse().
                    #     hold_pts.reverse()
                    #     holdidx = len(hold_pts)
                    #     for hp in hold_pts:
                    #         p = MovePoint.new(hp)
                    #         p.setAltitude(alt+star_alt)
                    #         p.setSpeed(actype.getSI(ACPERF.approach_speed))
                    #         p.setVSpeed(0)
                    #         p.setColor(POSITION_COLOR.HOLDING.value)
                    #         p.setMark(FLIGHT_PHASE.HOLDING.value)
                    #         p.setProp(FEATPROP.FLIGHT_PLAN_INDEX, i)
                    #         p.setProp("holding-pattern-idx", holdidx)
                    #         holdidx = holdidx - 1
                    #         revmoves.append(p)
                    #     logger.debug("..done (%d points added)" % (len(hold_pts)))
                    # else:
                    #     logger.debug("holding fix %s not found" % (self.holdingpoint))

                    fplnidx_rev = k

            if self.flight.flight_level > 100:
                # descent from FL100 to first approach point
                logger.debug("(rev) descent to star altitude")
                step = actype.descentApproach(convert.feet_to_meters(10000), arrapt_alt.in_m + star_alt.in_m)  # (t, d, altend)
                groundmv = groundmv + step[1]
                currpos, fplnidx_rev = moveOnLS(
                    coll=revmoves,
                    reverse=True,
                    fc=fplnrev,
                    fcidx=fplnidx_rev,
                    currpos=currpos,
                    dist=step[1],
                    alt=convert.feet_to_meters(10000),
                    speed=actype.getSI(ACPERF.approach_speed),
                    vspeed=actype.getSI(ACPERF.approach_vspeed),
                    color=POSITION_COLOR.DESCEND.value,
                    mark="descent_fl100_reached",
                    mark_tr=FLIGHT_PHASE.DESCEND.value,
                )

                if self.flight.flight_level > 240:
                    # descent from FL240 to FL100
                    logger.debug("(rev) descent to FL100")
                    step = actype.descentToFL100(convert.feet_to_meters(24000))  # (t, d, altend)
                    groundmv = groundmv + step[1]
                    currpos, fplnidx_rev = moveOnLS(
                        coll=revmoves,
                        reverse=True,
                        fc=fplnrev,
                        fcidx=fplnidx_rev,
                        currpos=currpos,
                        dist=step[1],
                        alt=convert.feet_to_meters(24000),
                        speed=actype.getSI(ACPERF.descentFL100_speed),
                        vspeed=actype.getSI(ACPERF.descentFL100_vspeed),
                        color=POSITION_COLOR.DESCEND.value,
                        mark="descent_fl240_reached",
                        mark_tr=FLIGHT_PHASE.DESCEND.value,
                    )

                    if self.flight.flight_level > 240:
                        # descent from cruise above FL240 to FL240
                        logger.debug("(rev) descent from cruise alt to FL240")
                        step = actype.descentToFL240(self.flight.getCruiseAltitude())  # (t, d, altend)
                        groundmv = groundmv + step[1]
                        currpos, fplnidx_rev = moveOnLS(
                            coll=revmoves,
                            reverse=True,
                            fc=fplnrev,
                            fcidx=fplnidx_rev,
                            currpos=currpos,
                            dist=step[1],
                            alt=self.flight.getCruiseAltitude(),
                            speed=actype.getSI(ACPERF.descentFL240_mach),
                            vspeed=actype.getSI(ACPERF.descentFL240_vspeed),
                            color=POSITION_COLOR.TOP_OF_DESCENT.value,
                            mark=FLIGHT_PHASE.TOP_OF_DESCENT.value,
                            mark_tr=FLIGHT_PHASE.DESCEND.value,
                        )

                else:
                    # descent from cruise below FL240 to FL100
                    logger.debug("(rev) descent from cruise alt under FL240 to FL100")
                    step = actype.descentToFL100(self.flight.getCruiseAltitude())  # (t, d, altend)
                    groundmv = groundmv + step[1]
                    currpos, fplnidx_rev = moveOnLS(
                        coll=revmoves,
                        reverse=True,
                        fc=fplnrev,
                        fcidx=fplnidx_rev,
                        currpos=currpos,
                        dist=step[1],
                        alt=self.flight.getCruiseAltitude(),
                        speed=actype.getSI(ACPERF.descentFL100_speed),
                        vspeed=actype.getSI(ACPERF.descentFL100_vspeed),
                        color=POSITION_COLOR.DESCEND.value,
                        mark=FLIGHT_PHASE.TOP_OF_DESCENT.value,
                        mark_tr=FLIGHT_PHASE.DESCEND.value,
                    )
            else:
                # descent from cruise below FL100 to approach alt
                logger.debug("(rev) descent from cruise alt under FL100 to approach alt")
                step = actype.descentApproach(self.flight.getCruiseAltitude(), arrapt_alt.in_m + approach_alt.in_m)  # (t, d, altend)
                groundmv = groundmv + step[1]
                currpos, fplnidx_rev = moveOnLS(
                    coll=revmoves,
                    reverse=True,
                    fc=fplnrev,
                    fcidx=fplnidx_rev,
                    currpos=currpos,
                    dist=step[1],
                    alt=self.flight.getCruiseAltitude(),
                    speed=actype.getSI(ACPERF.approach_speed),
                    vspeed=actype.getSI(ACPERF.approach_vspeed),
                    color=POSITION_COLOR.DESCEND.value,
                    mark=FLIGHT_PHASE.TOP_OF_DESCENT.value,
                    mark_tr=FLIGHT_PHASE.DESCEND.value,
                )

            # decelerate to descent speed smoothly
            DECELERATION_DISTANCE = 5000  # we reach cruise speed after 5km horizontal flight
            logger.debug("(rev) decelerate from cruise speed to first descent speed (which depends on alt...)")
            groundmv = groundmv + DECELERATION_DISTANCE
            currpos, fplnidx_rev = moveOnLS(
                coll=revmoves,
                reverse=True,
                fc=fplnrev,
                fcidx=fplnidx_rev,
                currpos=currpos,
                dist=DECELERATION_DISTANCE,
                alt=self.flight.getCruiseAltitude(),
                speed=cruise_speed,
                vspeed=0,
                color=POSITION_COLOR.DECELERATE.value,
                mark=FLIGHT_PHASE.LEAVE_CRUISE_SPEED.value,
                mark_tr="end_of_decelerate",
            )

            top_of_decent_idx = fplnidx_rev + 1  # we reach top of descent between idx and idx+1, so we cruise until idx+1
            logger.debug("(rev) reverse descent at %d after %f" % (top_of_decent_idx, groundmv))
            # we .reverse() array:
            top_of_decent_idx = len(fplnrev) - top_of_decent_idx - 1
            logger.debug("(rev) cruise until %d, descent after %d, remains %f to destination" % (top_of_decent_idx, top_of_decent_idx, groundmv))

            #
            #
            # PART 2.3: Join top of ascent to top of descent at cruise speed
            #           If airawys have restrictions, should adjust "stepped" climbs/desends
            #           to comply with airway restrictions.
            #           We copy waypoints from start of cruise to end of cruise
            logger.debug("cruise")
            if top_of_decent_idx > top_of_ascent_idx:
                # logger.debug("adding cruise: %d -> %d" % (top_of_ascent_idx, top_of_decent_idx))
                # add_cruise(top_of_ascent_idx, top_of_decent_idx)
                for i in range(top_of_ascent_idx, top_of_decent_idx):
                    wpt = fplnrev[i]
                    # logger.debug("adding cruise: %d %s" % (i, wpt.getProp(FEATPROP.PLAN_SEGMENT_TYPE)))

                    p = addMovepoint(
                        arr=self._premoves,
                        src=wpt,
                        alt=self.flight.getCruiseAltitude(),
                        speed=cruise_speed,
                        vspeed=0,
                        color=POSITION_COLOR.CRUISE.value,
                        mark=FLIGHT_PHASE.CRUISE.value,
                        ix=i,
                    )
                logger.debug("cruise added (+%d %d)" % (top_of_decent_idx - top_of_ascent_idx, len(self._premoves)))
            else:
                logger.warning("cruise too short (%d -> %d)" % (top_of_ascent_idx, top_of_decent_idx))

            logger.debug(f"descent added (+{len(revmoves)} {len(self._premoves)})")
            revmoves.reverse()
            self._premoves = self._premoves + revmoves
        # END if not (cruise_added or self.flight.arrival.has_stars() or self.flight.arrival.has_approaches())
        # In fact, END old method.

        idx = 0
        for f in self._premoves:
            f.setProp(FEATPROP.PREMOVE_INDEX, idx)
            idx = idx + 1

        logger.debug(f"doing speed control..")
        self.snav()
        logger.debug(f"..done")

        self._points = self._premoves  # for tabulate printing

        # printFeatures(self._premoves, "holding")
        logger.debug("terminated " + "=" * 30)
        return (True, "Movement::vnav completed")

    def standard_turns(self):
        # @todo: Should supress ST when turn is too small (< 10°) (done in st_flyby())
        #        Should supress ST when points too close (leg < 10 second move at constant speed)
        def turnRadius(speed):  # speed in m/s, returns radius in m
            return 120 * speed / (2 * pi)

        def should_do_st(f):
            mark = f.getProp(FEATPROP.MARK)
            return mark not in [FLIGHT_PHASE.TAKE_OFF.value, "end_initial_climb", FLIGHT_PHASE.TOUCH_DOWN.value, FLIGHT_PHASE.END_ROLLOUT.value]

        # Init, keep local pointer for convenience
        move_points = []

        # @todo: should fetch another reasonable value from aircraft performance.
        last_speed = convert.kmh_to_ms(convert.kn_to_kmh(kn=200))  # kn to km/h; and km/h to m/s

        # Add first point
        move_points.append(self._premoves[0])

        # Intermediate points
        # with open("test.geojson", "w") as fp:
        #     json.dump(FeatureCollection(features=self._premoves).to_geojson(), fp)
        for i in range(1, len(self._premoves) - 1):
            if not should_do_st(self._premoves[i]):
                logger.debug("skipping %d (special mark)" % (i))
                move_points.append(self._premoves[i])
            else:
                li = LineString([self._premoves[i - 1].coords(), self._premoves[i].coords()])
                lo = LineString([self._premoves[i].coords(), self._premoves[i + 1].coords()])

                s = self._premoves[i].speed()
                if s is None:
                    s = last_speed

                arc = None
                if self._premoves[i].flyOver():
                    arc = standard_turn_flyover(li, lo, turnRadius(s))  # unsufficiently tested..
                    # falls back on flyby (which works well)
                    logger.debug(f"standard_turn_flyover failed, fall back on standard_turn_flyby ({i})")
                    if arc is None:
                        arc = standard_turn_flyby(li, lo, turnRadius(s))
                else:
                    arc = standard_turn_flyby(li, lo, turnRadius(s))

                last_speed = s

                if arc is not None:
                    mid = arc[int(len(arc) / 2)]
                    mid.properties = self._premoves[i].properties
                    for p in arc:
                        move_points.append(MovePoint(geometry=p.geometry, properties=mid.properties))
                else:
                    # logger.debug(f"standard_turn_flyby failed, skipping standard turn ({i})")
                    move_points.append(self._premoves[i])

        # Add last point too
        move_points.append(self._premoves[-1])

        # Sets unique index on flight movement features
        idx = 0
        for f in move_points:
            f.setProp(FEATPROP.MOVE_INDEX, idx)
            f.setProp("flight-summary", str(self.flight))
            f.setProp("flight", self.flight.getInfo())
            idx = idx + 1

        self.setMovePoints(move_points)

        logger.debug(f"completed {len(self._premoves)}, {len(self.getMovePoints())} with standard turns")
        return (True, "Movement::standard_turns added")

    def interpolate(self):
        """
        Compute interpolated values for altitude and speed based on distance.
        This is a simple linear interpolation based on distance between points.
        Runs for flight portion of flight.
        """
        to_interp = self.getMovePoints()
        # before = []
        check = "altitude"
        logger.debug("interpolating..")
        for name in ["speed", "vspeed", "altitude"]:
            logger.debug(f"..{name}..")
            if name == check:
                before = list(map(lambda x: x.getProp(name), to_interp))
            status = doInterpolation(to_interp, name)
            if not status[0]:
                logger.warning(status[1])
        logger.debug("..done.")

        logger.debug("checking and transposing altitudes to geojson coordinates..")
        for f in to_interp:
            a = f.altitude()
            # if len(f.geometry["coordinates"]) == 2:
            #     a = f.altitude()
            #     if a is not None:
            #         f.geometry["coordinates"].append(float(a))
            #     else:
            #         logger.warning(f"no altitude? {f.getProp(FEATPROP.MOVE_INDEX)}.")
        logger.debug("..done.")

        # name = check
        # for i in range(len(to_interp)):
        #     v = to_interp[i].getProp(name) if to_interp[i].getProp(name) is not None and to_interp[i].getProp(name) != "None" else "none"
        #     logger.debug("%d: %s -> %s." % (i, before[i] if before[i] is not None else -1, v))

        # logger.debug("last point %d: %f, %f" % (len(self._move_poin), self._move_poin[-1].speed(), self._move_poin[-1].altitude()))
        # i = 0
        # for f in self._premoves:
        #     s = f.speed()
        #     a = f.altitude()
        #     logger.debug("alter: %d: %f %f" % (i, s if s is not None else -1, a if a is not None else -1))
        #     i = i + 1

        return (True, "Movement::interpolated speed and altitude")

    def add_wind(self):
        # Prepare wind data collection
        # 1. limit to flight movement bounding box
        ret = self.flight.managedAirport.weather_engine.prepare_enroute_winds(
            flight=self.flight
        )  # , use_gfs=True)  # caches expensive weather data for this flight
        if not ret:
            logger.warning(f"no wind")
            return (True, "Movement::add_wind cannot find wind data, ignoring wind")

        output = io.StringIO()
        print("\n", file=output)
        print(f"MOVEMENT", file=output)
        MARK_LIST = ["TIME", "TAS", "COURSE TH", "WIND SPEED", "WIND DIR", "GS", "GS DELTA", "COURSE", "COURSE DELTA", "HEADING", "COURSE-HEADING"]
        table = []

        fid = self.flight.getId()
        cnt1 = 0
        cnt2 = 0
        cnt3 = 0
        f0 = self.flight.getScheduledDepartureTime()
        for p in self.getMovePoints():
            if not p.getProp(FEATPROP.GROUNDED):
                cnt1 = cnt1 + 1
                ft = f0
                time = p.time()
                if time is not None:
                    ft = ft + timedelta(seconds=time)
                wind = self.flight.managedAirport.weather_engine.get_enroute_wind(flight_id=fid, lat=p.lat(), lon=p.lon(), alt=p.alt(), moment=ft)
                if wind is not None:
                    p.setProp(FEATPROP.WIND, wind)
                    cnt2 = cnt2 + 1
                    ## need to property adjust heading here
                    if wind.speed is not None:
                        if wind.direction is not None:
                            ac_speed = p.speed()
                            ac_course = p.course()
                            if ac_speed is not None and ac_course is not None:
                                p.setCourse(ac_course)
                                ac = (ac_speed, ac_course)
                                ws = (wind.speed, wind.direction)
                                (newac, gs) = adjust_speed_vector(ac, ws)  # gs[1] ~ ac_course
                                p.setSpeed(gs[0])
                                p.setProp(FEATPROP.TASPEED, ac_speed)
                                p.setHeading(newac[1])
                                # logger.debug(f"TAS={round(ac_speed)} COURSE={ac_course} + wind={[round(p) for p in ws]} => GS={newac[0]} COURSE={gs[1]}, HEADING={newac[1]}")
                                table.append(
                                    (
                                        p.time(),
                                        round(ac_speed),
                                        ac_course,
                                        ws[0],
                                        ws[1],
                                        gs[0],
                                        gs[0] - ac_speed,
                                        gs[1],
                                        round(ac_course - gs[1], 2),
                                        newac[1],
                                        round(gs[1] - newac[1], 2),
                                    )
                                )
                            else:
                                logger.debug(f"missing aircraft speed or heading ({ac_speed}, {ac_course})?")
                            cnt3 = cnt3 + 1
                        else:
                            logger.debug("wind is variable direction, do not add wind")
                    else:
                        logger.debug("no wind speed, do not add wind")
                else:
                    logger.debug("no wind info")

        table = sorted(table, key=lambda x: x[0])  # absolute emission time
        print(tabulate(table, headers=MARK_LIST), file=output)

        contents = output.getvalue()
        output.close()
        logger.debug(f"{contents}")

        ret = self.flight.managedAirport.weather_engine.forget_enroute_winds(flight=self.flight)
        logger.warning(f"wind added ({cnt2/cnt1/len(self.getMovePoints())})")
        return (True, "Movement::add_wind added")

    def time(self):
        """
        Time 0 is start of roll for takeoff (Departure) or takeoff from origin airport (Arrival).
        Last time is touch down at destination (Departure) or end of roll out (Arrival).
        """
        if self.getMovePoints() is None:
            return (False, "Movement::time no move")

        status = doTime(self.getMovePoints())
        if not status[0]:
            logger.warning(status[1])
            return status

        for f in self.getMovePoints():  # we save a copy of the movement timing for rescheduling
            f.setProp(FEATPROP.SAVED_TIME, f.time())

        logger.debug(f"movement timed")

        return (True, "Movement::time computed")

    def tabulateFlightMovement(self, title: str = "FLIGHT MOVEMENT"):
        def alt_ft(a):
            return "" if a is None else str(round(convert.meters_to_feet(a)))

        def speed_kn(a):
            return "" if a is None else str(round(convert.ms_to_kn(a)))

        def speed_fpm(a):
            return "" if a is None else str(round(convert.ms_to_fpm(a)))

        output = io.StringIO()
        print("\n", file=output)
        print(f"{title}", file=output)
        HEADER = [
            "INDEX",
            "MARK",
            "FP IDX",
            "WAYPOINT",
            "RESTRICTIONS",
            "DISTANCE",
            "TOTAL DISTANCE",
            "ALT (m)",
            "SPEED (m/s)",
            "V/S (m/s)",
            "ALT (ft)",
            "SPEED (kn)",
            "V/S (ft/min)",
            "COURSE",
            "COMMENTS",
        ]  # long comment to provoke wrap :-)
        table = []

        fid = self.flight.getId()
        f0 = self.flight.getScheduledDepartureTime()
        ft = f0
        total_dist = 0
        last_point = None
        idx = 0
        for w in self.getMovePoints():
            d = 0
            if last_point is not None:
                d = distance(last_point, w)
                total_dist = total_dist + d

            speed_ok = ""
            alt_ok = ""
            restriction = w.getProp("restriction")
            if restriction is not None and restriction != "":  # has restriction...
                r = Restriction.parse(restriction)
                if w.speed() is not None and not r.checkSpeed(w):
                    speed_ok = " ***"
                if w.altitude() is not None and not r.checkAltitude(w.geometry):
                    alt_ok = " ***"

            table.append(
                [
                    idx,
                    w.getMark(),
                    w.getProp(FEATPROP.FLIGHT_PLAN_INDEX),
                    w.getId(),
                    restriction,
                    round(d, 1),
                    round(total_dist),
                    round(w.altitude()) if w.altitude() is not None else "",
                    w.speed(),
                    w.vspeed(),
                    alt_ft(w.altitude()) + alt_ok,
                    speed_kn(w.speed()) + speed_ok,
                    speed_fpm(w.vspeed()),
                    w.course(),
                    w.comment(),
                ]
            )
            last_point = w
            idx = idx + 1

        table = sorted(table, key=lambda x: x[0])  # absolute emission time
        print(tabulate(table, headers=HEADER), file=output)

        contents = output.getvalue()
        output.close()
        return contents

    def taxi(self):
        return (False, "Movement::taxi done")

    def taxiInterpolateAndTime(self):
        """
        Time 0 is start of pushback (Departure) or end of roll out (Arrival).
        Last time is take off hold (Departure) or parking (Arrival).
        """
        if self.taxipos is None:
            return (False, "Movement::taxiInterpolateAndTime no move")

        logger.debug("interpolate speed..")
        status = doInterpolation(self.taxipos, "speed")
        if not status[0]:
            logger.warning(status[1])
            return status

        logger.debug("..compute course..")
        status = compute_headings(self.taxipos)
        if not status[0]:
            logger.warning(status[1])
            return status

        logger.debug("..compute time..")
        status = doTime(self.taxipos)
        if not status[0]:
            logger.warning(status[1])
            return status

        for f in self.taxipos:
            f.setProp(FEATPROP.SAVED_TIME, f.time())
            f.setProp(FEATPROP.GROUNDED, True)

        logger.debug("..done.")

        return (True, "Movement::taxiInterpolateAndTime done")

    def add_tmo(self, TMO: float = convert.nm_to_km(10), mark: str = FLIGHT_PHASE.TEN_MILE_OUT.value):
        # We add a TMO point (Ten (nautical) Miles Out). Should be set before we interpolate.
        # TMO = convert.nm_to_km(10)  # km
        move_points = super().getMovePoints()  # we don't need the taxi points
        idx = len(move_points) - 1  # last is end of roll, before last is touch down.
        totald = 0
        prev = 0
        # If necessary, use "bird flight distance" (beeline? crow flight?) with
        # while ditance(move_points[idx], move_points[-2]) < TMO and idx > 1:  # last is end of roll, before last is touch down.)
        while totald < TMO and idx > 1:
            idx = idx - 1
            d = distance(move_points[idx], move_points[idx - 1])
            prev = totald
            totald = totald + d
            # logger.debug("add_tmo: %d: d=%f, t=%f" % (idx, d, totald))
        if idx >= 0:
            # idx points at
            left = TMO - prev
            # logger.debug("add_tmo: %d: left=%f, TMO=%f" % (idx, left, TMO))
            brng = bearing(move_points[idx], move_points[idx - 1])
            tmopt = destination(move_points[idx], left, brng)

            tmomp = MovePoint(geometry=tmopt.geometry, properties={})
            tmomp.setMark(mark)

            # throw stone distance, not path
            d = distance(tmomp, move_points[-2])  # last is end of roll, before last is touch down

            move_points.insert(idx, tmomp)
            if prev == 0:
                prev = d
            logger.debug(f"added at ~{d:f} km, ~{convert.km_to_nm(d)} nm from touch down (path is {prev:f} km, {convert.km_to_nm(prev)} nm)")

            self.addMessage(FlightMessage(subject=f"{self.flight_id} {mark}", flight=self, sync=mark))
        else:
            logger.warning(f"less than {TMO} miles, no {mark} point added")

        return (True, "Movement::add_tmo added")

    def add_faraway(self, FARAWAY: float = convert.nm_to_km(100)):
        # We add a FARAWAY point when flight is at FARAWAY from begin of roll (i.e. at FARAWAY from airport).
        # FARAWAY is ~100 miles away following airways (i.e. 100 miles of flight to go),
        # not in straght line, although we could adjust algorithm if needed.
        return self.add_tmo(TMO=FARAWAY, mark=FLIGHT_PHASE.FAR_AWAY.value)

    def get_timed_flight_plan(self) -> list:
        """Now that we have timed the trip and that each point has a speed,
        it is possible to build a timed flight plan
        """
        fpidx = set([f.getProp(FEATPROP.FLIGHT_PLAN_INDEX) for f in self.flight.flightplan_wpts])
        done = []
        ret = []
        for f in self.getMovePoints():
            i = f.getProp(FEATPROP.FLIGHT_PLAN_INDEX)
            if i is not None and i not in done:
                done.append(i)
                ret.append(f)
                if i not in fpidx:
                    logger.warning(f"invalid index {i} in flight plan")
                    print(json.dumps(f.to_geojson(), indent=2))
                else:
                    fpidx.remove(i)
        ret = sorted(ret, key=lambda f: f.getProp(FEATPROP.FLIGHT_PLAN_INDEX))
        logger.debug(f"extracted {len(ret)} flight plan waypoints")
        return ret

    def tabulateFlightPlan(self):
        def alt_ft(a):
            return "" if a is None else str(round(convert.meters_to_feet(a)))

        def speed_kn(a):
            return "" if a is None else str(round(convert.ms_to_kn(a)))

        def speed_fpm(a):
            return "" if a is None else str(round(convert.ms_to_fpm(a)))

        output = io.StringIO()
        print("\n", file=output)
        print(f"TIMED FLIGHT PLAN", file=output)
        HEADER = [
            "INDEX",
            "MARK",
            "WAYPOINT",
            "RESTRICTIONS",
            "DISTANCE",
            "TOTAL DISTANCE",
            "TIME (s)",
            "TOTAL TIME (s)",
            "DATE TIME",
            "ALT (m)",
            "SPEED (m/s)",
            "V/S (m/s)",
            "ALT (ft)",
            "SPEED (kn)",
            "V/S (ft/min)",
            "COURSE",
            "COMMENTS",
        ]  # long comment to provoke wrap :-)
        table = []

        fid = self.flight.getId()
        f0 = self.flight.getScheduledDepartureTime()
        start = datetime.now().timestamp()
        if self.flight.estimated_dt is not None:
            start = self.flight.scheduled_dt.timestamp()
        elif self.flight.estimated_dt is not None:
            start = self.flight.scheduled_dt.timestamp()
        ft = f0
        last_ti = 0
        total_dist = 0
        last_point = None
        idx = 0
        for w in self.get_timed_flight_plan():
            d = 0
            if last_point is not None:
                d = distance(last_point, w)
                total_dist = total_dist + d

            speed_ok = ""
            alt_ok = ""
            restriction = w.getProp("restriction")
            if restriction is not None and restriction != "":  # has restriction...
                r = Restriction.parse(restriction)
                if w.speed() is not None and not r.checkSpeed(w):
                    speed_ok = " ***"
                if w.altitude() is not None and not r.checkAltitude(w.geometry):
                    alt_ok = " ***"

            ti = w.time()
            fti = datetime.fromtimestamp(start + ti).replace(microsecond=0).isoformat()

            table.append(
                [
                    w.getProp(FEATPROP.FLIGHT_PLAN_INDEX),
                    w.getMark(),
                    w.getId(),
                    restriction,
                    round(d, 1),
                    round(total_dist),
                    timedelta(seconds=int(ti - last_ti)),
                    timedelta(seconds=int(ti)),
                    fti,
                    round(w.altitude()) if w.altitude() is not None else "",
                    w.speed(),
                    w.vspeed(),
                    alt_ft(w.altitude()) + alt_ok,
                    speed_kn(w.speed()) + speed_ok,
                    speed_fpm(w.vspeed()),
                    w.course(),
                    w.comment(),
                ]
            )
            last_point = w
            last_ti = ti
            idx = idx + 1

        table = sorted(table, key=lambda x: x[0])  # absolute emission time
        print(tabulate(table, headers=HEADER), file=output)

        contents = output.getvalue()
        output.close()
        return contents

    def saveSO6(self):
        """
        Save GSE paths to file for emitted positions for python traffic analysis
        """
        flight_plan = self.get_timed_flight_plan()
        logger.debug(f"flight plan has {len(flight_plan)} positions, saving..")

        ident = self.getId()
        basedir = os.path.join(MANAGED_AIRPORT_AODB, FLIGHT_DATABASE)
        if not os.path.exists(basedir):
            os.mkdir(basedir)
            logger.info(f"directory {basedir} did not exist. created.")

        ls = toSO6(flight_plan)
        filename = os.path.join(basedir, ident + "-" + FILE_FORMAT.FLIGHT_PLAN.value + ".so6")
        with open(filename, "w") as fp:
            fp.write(ls)
        logger.debug(f"..saved {ident} timed flight plan")

        return (True, "Move::saveSO6 saved")


class ArrivalMove(FlightMovement):
    """
    Movement for an arrival flight
    """

    def __init__(self, flight: Flight, airport: ManagedAirportBase):
        FlightMovement.__init__(self, flight=flight, airport=airport)

    def getMovePoints(self):
        # That's where getMovePoints() differs from getPoints()
        base = super().getMovePoints()
        if len(base) == 0:
            logger.warning(f"({type(self).__name__}): no base points")
            return base  # len(base) == 0
        if len(self.taxipos) > 0:  # it's ok, they can be added later
            test = self.taxipos[0].getProp(FEATPROP.SAVED_TIME)
            if test is not None:
                logger.debug(f"adding {len(self.taxipos)} taxi points")
                start = self.taxipos[-1].time()  # take time of last event of flight
                for f in self.taxipos:
                    f.setTime(start + f.getProp(FEATPROP.SAVED_TIME))
            else:
                logger.debug(f"{len(self.taxipos)} taxi points have no timing yet")
        # logger.debug(f"returning {len(base)} base positions and {len(self.taxipos)} taxi positions ({type(self).__name__})")
        return base + self.taxipos

    def taxi(self):
        """
        Compute taxi path for arrival, from roll out position, to runway exit to parking.
        """
        show_pos = False
        fc = []

        endrolloutpos = MovePoint.new(self.end_rollout)
        endrolloutpos.setSpeed(TAXI_SPEED)
        endrolloutpos.setColor("#880088")  # parking
        endrolloutpos.setMark("end rollout")
        fc.append(endrolloutpos)

        rwy = self.flight.rwy
        rwy_threshold = rwy.getPoint()
        landing_distance = distance(rwy_threshold, endrolloutpos)
        rwy_exit = self.airport.closest_runway_exit(rwy.name, landing_distance)

        taxi_start = self.airport.taxiways.nearest_point_on_edge(rwy_exit)
        if show_pos:
            logger.debug(f"taxi in: taxi start: {taxi_start}")
        else:
            logger.debug(f"taxi in: {rwy.name}-{self.flight.ramp.getProp('name')} " + "=" * 30)
        if taxi_start[0] is None:
            logger.warning("taxi in: could not find taxi start")
        taxistartpos = MovePoint.new(taxi_start[0])
        taxistartpos.setSpeed(TAXI_SPEED)
        taxistartpos.setColor("#880088")  # parking
        taxistartpos.setMark("taxi start")
        fc.append(taxistartpos)

        taxistart_vtx = self.airport.taxiways.nearest_vertex(taxi_start[0])
        if show_pos:
            logger.debug(f"taxi in: taxi start vtx: {taxistart_vtx}")
        if taxistart_vtx[0] is None:
            logger.warning("taxi in: could not find taxi start vertex")
        taxistartpos = MovePoint.new(taxistart_vtx[0])
        taxistartpos.setSpeed(TAXI_SPEED)
        taxistartpos.setColor("#880088")  # parking
        taxistartpos.setMark("taxi start vertex")
        fc.append(taxistartpos)

        parking = self.flight.ramp
        if show_pos:
            logger.debug(f"taxi in: parking: {parking}")
        # we call the move from packing position to taxiway network the "parking entry"
        parking_entry = self.airport.taxiways.nearest_point_on_edge(parking)
        if show_pos:
            logger.debug(f"taxi in: parking_entry: {parking_entry[0]}")

        if parking_entry[0] is None:
            logger.warning("taxi in: could not find parking entry")

        parkingentry_vtx = self.airport.taxiways.nearest_vertex(parking_entry[0])
        if parkingentry_vtx[0] is None:
            logger.warning("taxi in: could not find parking entry vertex")
        if show_pos:
            logger.debug(f"taxi in: parkingentry_vtx: {parkingentry_vtx[0]} ")

        taxi_ride = Route(self.airport.taxiways, taxistart_vtx[0].id, parkingentry_vtx[0].id)
        if taxi_ride.found():
            for vtx in taxi_ride.get_vertices():
                # vtx = self.airport.taxiways.get_vertex(vid)
                taxipos = MovePoint.new(vtx)
                taxipos.setSpeed(TAXI_SPEED)
                taxipos.setColor("#880000")  # taxi
                taxipos.setMark("taxi")
                taxipos.setProp("_taxiways", vtx.id)
                fc.append(taxipos)
            fc[-1].setMark("taxi end vertex")
        else:
            logger.warning("taxi in: no taxi route found")

        parkingentrypos = MovePoint.new(parking_entry[0])
        parkingentrypos.setSpeed(SLOW_SPEED)
        parkingentrypos.setColor("#880088")  # parking entry, is on taxiway network
        parkingentrypos.setMark("taxi end")
        fc.append(parkingentrypos)

        # This is the last point, we make sure available info is in props
        parkingpos = MovePoint.new(parking)
        parkingpos.setSpeed(0)
        parkingpos.setVSpeed(0)
        parkingpos.setAltitude(self.airport.altitude())
        parkingpos.setColor("#880088")  # parking
        parkingpos.setMark(FLIGHT_PHASE.ONBLOCK.value)
        fc.append(parkingpos)

        ac = self.flight.aircraft
        self.addMessage(
            FlightMessage(
                subject=f"ACARS: {ac.icao24} {FLIGHT_PHASE.ONBLOCK.value} at {self.flight.ramp.getName()}", flight=self, sync=FLIGHT_PHASE.ONBLOCK.value
            )
        )

        if show_pos:
            logger.debug(f"taxi in: taxi end: {parking}")
        else:
            logger.debug(f"taxi in: taxi end: parking {parking.getProp('name')}")

        idx = 0
        for f in self.taxipos:
            f.setProp(FEATPROP.PLAN_SEGMENT_TYPE, FLIGHT_PHASE.TAXI_IN.value)
            f.setProp(FEATPROP.TAXI_INDEX, idx)
            idx = idx + 1

        self.taxipos = fc
        logger.debug(f"taxi in: taxi {len(self.taxipos)} moves")

        return (True, "ArrivalMove::taxi completed")


class DepartureMove(FlightMovement):
    """
    Movement for an departure flight
    """

    def __init__(self, flight: Flight, airport: ManagedAirportBase):
        FlightMovement.__init__(self, flight=flight, airport=airport)

    def getMovePoints(self):
        # That's where getMovePoints() differs from getPoints()
        start = 0
        if len(self.taxipos) > 0:  # it's ok, they can be added later
            logger.debug(f"({type(self).__name__}): starting with {len(self.taxipos)} taxi positions")
            start = self.taxipos[-1].time()  # time of flight starts at end of taxi

        base = super().getMovePoints()
        if len(base) > 0:
            test = base[0].getProp(FEATPROP.SAVED_TIME)
            if test is not None:
                for f in base:
                    f.setTime(start + f.getProp(FEATPROP.SAVED_TIME))
            else:
                logger.debug(f"{len(self.taxipos)} base points have no timing yet")
        else:
            logger.warning(f"({type(self).__name__}): no base position")
        logger.debug(f"getting {len(self.taxipos)} taxi positions and {len(base)} base positions ({type(self).__name__})")
        return self.taxipos + base

    def taxi(self):
        """
        Compute taxi path for departure, from parking to take-off hold location.
        """
        show_pos = False
        fc = []

        parking = self.flight.ramp
        if show_pos:
            logger.debug(f"taxi out: parking: {parking}")
        else:
            logger.debug(f"taxi out: {parking.getProp('name')}-{self.flight.rwy.name if self.flight.rwy is not None else 'no runway'} " + "=" * 30)
        # This is the first point, we make sure available info is in props
        parkingpos = MovePoint.new(parking)
        parkingpos.setSpeed(0)
        parkingpos.setVSpeed(0)
        parkingpos.setAltitude(self.airport.altitude())
        parkingpos.setColor("#880088")  # parking
        parkingpos.setMark(FLIGHT_PHASE.OFFBLOCK.value)
        fc.append(parkingpos)

        ac = self.flight.aircraft
        self.addMessage(
            FlightMessage(
                subject=f"ACARS: {ac.icao24} {FLIGHT_PHASE.OFFBLOCK.value} from {self.flight.ramp.getName()}", flight=self, sync=FLIGHT_PHASE.OFFBLOCK.value
            )
        )

        if show_pos:
            logger.debug(f"taxi out: taxi start: {parkingpos}")

        # we call the move from packing position to taxiway network the "pushback"
        pushback_end = self.airport.taxiways.nearest_point_on_edge(parking)
        if show_pos:
            logger.debug(f"taxi out: pushback_end: {pushback_end[0]}")
        if pushback_end[0] is None:
            logger.warning("taxi out: could not find pushback end")

        pushbackpos = MovePoint.new(pushback_end[0])
        pushbackpos.setSpeed(SLOW_SPEED)
        pushbackpos.setColor("#880088")  # parking
        pushbackpos.setMark(FLIGHT_PHASE.PUSHBACK.value)
        fc.append(pushbackpos)

        pushback_vtx = self.airport.taxiways.nearest_vertex(pushback_end[0])
        if show_pos:
            logger.debug(f"taxi out: pushback_vtx: {pushback_vtx[0]}")
        if pushback_vtx[0] is None:
            logger.warning("taxi out: could not find pushback end vertex")

        last_vtx = pushback_vtx

        logger.debug(f"taxi out: taxing from pushback-hold..")
        # Normally, we then taxi from pushback to takeoff-hold:
        # pushb -> taxi -> takeoff-hold.
        # Now we insert takeoff queue position if available.
        # pushb -> queue3 -> queue2 -> queue1 -> queue0 (=runway-hold) -> takeoff-hold
        rwy = self.flight.rwy

        if self.airport.has_takeoff_queue(rwy.name):
            backup_vtx = pushback_vtx
            has_issues = False
            qpts = self.airport.takeoff_queue_points(rwy.name)  # should not be none...
            qnum = len(qpts) - 1
            logger.debug(f"taxi out: adding queue {qnum} points..")

            while qnum >= 0:
                # Taxi from last_vtx to next queue point (in reverse order)
                #
                queuepnt = self.airport.queue_point(rwy.name, qnum)
                queuerwy = self.airport.taxiways.nearest_point_on_edge(queuepnt)
                if show_pos:
                    logger.debug(f"taxi out: start of queue point: {queuerwy[0]}")
                if queuerwy[0] is None:
                    logger.warning(f"taxi out: could not find queue point {qnum}")

                queuerwy_vtx = self.airport.taxiways.nearest_vertex(queuerwy[0])
                if show_pos:
                    logger.debug(f"taxi out: queuerwy_vtx {queuerwy_vtx[0]}")
                if queuerwy_vtx[0] is None:
                    logger.warning(f"taxi out: could not find queue vertex {qnum}")

                taxi_ride = Route(self.airport.taxiways, last_vtx[0].id, queuerwy_vtx[0].id)
                if taxi_ride.found():
                    for vtx in taxi_ride.get_vertices():
                        taxipos = MovePoint.new(vtx)
                        taxipos.setSpeed(TAXI_SPEED)
                        taxipos.setColor("#880000")  # taxi
                        taxipos.setMark("taxi")
                        taxipos.setProp("_taxiways", vtx.id)
                        fc.append(taxipos)
                    fc[-1].setMark("taxi-hold")
                    fc[-1].setProp("taxi-hold", qnum)
                    logger.debug(f"taxi out: added route to queue point {qnum}")
                else:
                    has_issues = True
                    logger.warning(f"taxi out: no taxi route found to queue point {qnum}")

                last_vtx = queuerwy_vtx
                qnum = qnum - 1

            # last_vtx is last queue position (qnum=0)
            if has_issues:
                logger.warning(f"taxi out: .. had issues adding queue points, skipping queueing")
                last_vtx = backup_vtx
            else:
                logger.debug(f"taxi out: .. added queue points")

        # Taxi from last_vtx to takeoff-hold
        #
        logger.debug(f"taxi out: taxing to takeoff-hold")
        taxi_end = self.airport.taxiways.nearest_point_on_edge(self.takeoff_hold)
        if show_pos:
            logger.debug(f"taxi out: taxi_end: {taxi_end[0]}")
        if taxi_end[0] is None:
            logger.warning("taxi out: could not find taxi end")

        taxiend_vtx = self.airport.taxiways.nearest_vertex(taxi_end[0])
        if show_pos:
            logger.debug(f"taxiend_vtx {taxiend_vtx[0]}")
        if taxiend_vtx[0] is None:
            logger.warning("taxi out: could not find taxi end vertex")

        taxi_ride = Route(self.airport.taxiways, last_vtx[0].id, taxiend_vtx[0].id)
        if taxi_ride.found():
            for vtx in taxi_ride.get_vertices():
                taxipos = MovePoint.new(vtx)
                taxipos.setSpeed(TAXI_SPEED)
                taxipos.setColor("#880000")  # taxi
                taxipos.setMark("taxi")
                taxipos.setProp("_taxiways", vtx.id)
                fc.append(taxipos)
            fc[-1].setMark("runway hold")
        else:
            logger.warning("taxi out: no taxi route found to runway hold")

        taxiendpos = MovePoint.new(taxi_end[0])
        taxiendpos.setSpeed(TAXI_SPEED)
        taxiendpos.setColor("#880088")  # parking
        taxiendpos.setMark("taxi end")
        fc.append(taxiendpos)

        takeoffholdpos = MovePoint.new(self.takeoff_hold)
        takeoffholdpos.setSpeed(0)
        takeoffholdpos.setColor("#880088")  # parking
        takeoffholdpos.setMark("takeoff hold")
        fc.append(takeoffholdpos)

        if show_pos:
            logger.debug(f"taxi out: taxi end: {takeoffholdpos}")
        else:
            rwy_name = self.flight.rwy.name if self.flight.rwy is not None else "no runway"
            logger.debug(f"taxi out: taxi end: holding for runway {rwy_name}")

        self.taxipos = fc
        logger.debug(f"taxi out: taxi {len(self.taxipos)} moves")

        idx = 0
        for f in self.taxipos:
            f.setProp(FEATPROP.PLAN_SEGMENT_TYPE, FLIGHT_PHASE.TAXI_OUT.value)
            f.setProp(FEATPROP.TAXI_INDEX, idx)
            idx = idx + 1

        return (True, "DepartureMove::taxi completed")


class TowMove(Movement):
    """
    Movement build the detailed path of the aircraft, both on the ground (taxi) and in the air,
    from takeoff to landing and roll out.
    """

    def __init__(self, flight: Flight, newramp: "Ramp", airport: ManagedAirportBase):
        Movement.__init__(self, airport=airport, reason=Flight)
        self.flight = flight
        self.flight_id = self.flight.getId()
        self.is_arrival = self.flight.is_arrival()
        self.newramp = newramp
        self.tows = []  # list of tow movements

    def tow(self):
        """
        Tow a plane from its current ramp to the new ramp.
        This operation occurs moment minutes before OFFBLOCK (on departure) or after ONBLOCK (on arrival) time.
        Sets the flight ramp to newramp after movement.

        :param      newramp:  The newramp
        :type       newramp:  { type_description }
        :param      moment:   The moment
        :type       moment:   int
        """
        show_pos = False
        fc = []  # feature collection of tow movement
        # current ramp
        parking = self.flight.ramp
        if show_pos:
            logger.debug(f"parking: {parking}")
        else:
            logger.debug(f"tow start: parking {parking.getProp('name')}")
        # This is the first point, we make sure available info is in props
        parkingpos = MovePoint.new(parking)
        parkingpos.setSpeed(0)
        parkingpos.setVSpeed(0)
        parkingpos.setAltitude(self.airport.altitude())
        parkingpos.setColor("#880088")  # parking
        parkingpos.setMark(FLIGHT_PHASE.OFFBLOCK.value)
        fc.append(parkingpos)
        if show_pos:
            logger.debug(f"tow start: {parkingpos}")

        ac = self.flight.aircraft
        self.addMessage(
            FlightMessage(
                subject=f"ACARS: {ac.icao24} {FLIGHT_PHASE.OFFBLOCK.value} from {self.flight.ramp.getName()}", flight=self, sync=FLIGHT_PHASE.OFFBLOCK.value
            )
        )

        # we call the move from packing position to taxiway network the "pushback"
        pushback_end = self.airport.taxiways.nearest_point_on_edge(parking)
        if show_pos:
            logger.debug(f"pushback_end: {pushback_end[0]}")
        if pushback_end[0] is None:
            logger.warning("could not find pushback end")

        pushbackpos = MovePoint.new(pushback_end[0])
        pushbackpos.setSpeed(SLOW_SPEED)
        pushbackpos.setColor("#880088")  # parking
        pushbackpos.setMark(FLIGHT_PHASE.PUSHBACK.value)
        fc.append(pushbackpos)

        pushback_vtx = self.airport.taxiways.nearest_vertex(pushback_end[0])
        if show_pos:
            logger.debug(f"pushback_vtx: {pushback_vtx[0]}")
        if pushback_vtx[0] is None:
            logger.warning("could not find pushback end vertex")

        # new ramp
        newparking = self.newramp
        if show_pos:
            logger.debug(f"new parking: {newparking}")
        # we call the move from packing position to taxiway network the "parking entry"
        newparking_entry = self.airport.taxiways.nearest_point_on_edge(newparking)
        if show_pos:
            logger.debug(f"new parking_entry: {newparking_entry[0]}")

        if newparking_entry[0] is None:
            logger.warning("could not find parking entry")

        newparkingentry_vtx = self.airport.taxiways.nearest_vertex(newparking_entry[0])
        if newparkingentry_vtx[0] is None:
            logger.warning("could not find parking entry vertex")
        if show_pos:
            logger.debug(f"parkingentry_vtx: {newparkingentry_vtx[0]} ")

        tow_ride = Route(self.airport.taxiways, pushback_vtx[0].id, newparkingentry_vtx[0].id)
        if tow_ride.found():
            for vtx in tow_ride.get_vertices():
                TOW_SPEED = TAXI_SPEED / 2  # hum.
                # vtx = self.airport.taxiways.get_vertex(vid)
                towpos = MovePoint.new(vtx)
                towpos.setSpeed(TOW_SPEED)
                towpos.setColor("#888800")  # tow
                towpos.setMark("tow")
                towpos.setProp("_taxiways", vtx.id)
                fc.append(towpos)
            fc[-1].setMark("tow end vertex")
        else:
            logger.warning("no tow route found")

        newparkingentrypos = MovePoint.new(newparking_entry[0])
        newparkingentrypos.setSpeed(SLOW_SPEED)
        newparkingentrypos.setColor("#880088")  # parking entry, is on taxiway network
        newparkingentrypos.setMark("tow end")
        fc.append(newparkingentrypos)

        # This is the last point, we make sure available info is in props
        newparkingpos = MovePoint.new(parking)
        newparkingpos.setSpeed(0)
        newparkingpos.setVSpeed(0)
        newparkingpos.setAltitude(self.airport.altitude())
        newparkingpos.setColor("#880088")  # parking
        newparkingpos.setMark(FLIGHT_PHASE.ONBLOCK.value)
        fc.append(newparkingpos)

        if show_pos:
            logger.debug(f"end: {newparking}")
        else:
            logger.debug(f"end: parking {newparking.getProp('name')}")

        for f in fc:
            f.setProp(FEATPROP.GROUNDED, True)

        tow = {"from": self.flight.ramp, "to": self.newramp, "move": fc}
        self.tows.append(tow)  ## self.tows is array of tows since there might be many tows.
        self.flight.ramp = self.newramp
        logger.info(
            f"FlightMovement::tow completed: flight {self.flight_id}: from {tow['from'].getId()} to {tow['to'].getId()}"
            + f" at @todo minutes {'after onblock' if self.is_arrival else 'before offblock'}"
        )

        logger.debug(f"{len(fc)} moves")

        return (True, "FlightMovement::tow completed")
