"""
A succession of positions where the aircraft passes. Includes taxi and takeoff or landing and taxi.
"""

import os
import io
import json
import logging
import copy
from math import dist, pi
from datetime import timedelta
from functools import reduce

from tabulate import tabulate

from emitpy.airspace.restriction import Restriction
from emitpy.geo.turf import LineString, FeatureCollection, Feature, saveGeoJSON
from emitpy.geo.turf import distance, destination, bearing
from emitpy.flight import Flight, FLIGHT_SEGMENT
from emitpy.airport import ManagedAirportBase
from emitpy.aircraft import ACPERF
from emitpy.geo import MovePoint, Movement
from emitpy.geo import moveOn, cleanFeatures, asLineString, toKML, adjust_speed_vector
from emitpy.graph import Route
from emitpy.utils import FT, NAUTICAL_MILE, compute_headings
from emitpy.constants import POSITION_COLOR, FEATPROP, TAXI_SPEED, SLOW_SPEED
from emitpy.constants import FLIGHT_DATABASE, FLIGHT_PHASE, FILE_FORMAT, MOVE_TYPE
from emitpy.parameters import MANAGED_AIRPORT_AODB
from emitpy.message import FlightMessage
from emitpy.utils import interpolate as doInterpolation, compute_time as doTime, toKmh, toMs, toMeter, toNm, toFPM
from .standardturn import standard_turn_flyby, standard_turn_flyover

logger = logging.getLogger("FlightMovement")


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
        status = self.vnav()
        if not status[0]:
            logger.warning(status[1])
            return status

        logger.debug(self.tabulateMovement())
        # #####################################################
        #
        #
        logger.debug(f"flight {len(self.getMovePoints())} points, taxi {len(self.taxipos)} points")
        return (True, "FlightMovement::TEMPORARY completed")
        #
        #
        # #####################################################

        status = self.standard_turns()
        if not status[0]:
            logger.warning(status[1])
            return status

        if self.flight.is_arrival():
            status = self.add_tmo()
            if not status[0]:
                logger.warning(status[1])
                return status

            status = self.add_faraway()
            if not status[0]:
                logger.warning(status[1])
                return status

        status = self.interpolate()
        if not status[0]:
            logger.warning(status[1])
            return status

        res = compute_headings(self.getMovePoints())
        if not res[0]:
            logger.warning(status[1])
            return res

        status = self.time()  # sets the time for gross approximation
        if not status[0]:
            logger.warning(status[1])
            return status

        duration0 = self.getMovePoints()[-1].time()
        logger.debug(f"flight duration without winds: {duration0}")

        tb = []
        for p in self.getMovePoints():
            tb.append(p.time())

        status = self.add_wind()  # refines speeds
        if not status[0]:
            logger.warning(status[1])
            return status

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

        status = self.taxi()
        if not status[0]:
            logger.warning(status[1])
            return status

        status = self.taxiInterpolateAndTime()
        if not status[0]:
            logger.warning(status[1])
            return status
        # printFeatures(self.taxipos, "after taxi")

        logger.debug(self.tabulateMovement2())

        logger.debug(f"flight {len(self.getMovePoints())} points, taxi {len(self.taxipos)} points")
        return (True, "FlightMovement::move completed")

    def saveFile(self):
        """
        Save flight paths to 3 files for flight plan, detailed movement, and taxi path.
        Save a technical json file which can be loaded later, and GeoJSON files for display.
        @todo should save file format version number.
        """
        basename = os.path.join(MANAGED_AIRPORT_AODB, FLIGHT_DATABASE, self.flight_id)
        LINESTRING_EXTENSION = "_ls"

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
        if len(self.flight.flightplan_wpts) > 1:
            ls = Feature(geometry=asLineString(self.flight.flightplan_wpts))
            saveMe(self.flight.flightplan_wpts + [ls], FILE_FORMAT.FLIGHT_PLAN.value)

        # saveMe(self._premoves, "2-flight")
        if len(self._premoves) > 1:
            ls = Feature(geometry=asLineString(self._premoves))
            saveMe(self._premoves + [ls], FILE_FORMAT.FLIGHT.value)

        # saveMe(self.getMovePoints(), "3-move")
        move_points = self.getMovePoints()
        if len(move_points) > 1:
            ls = Feature(geometry=asLineString(move_points))
            saveMe(move_points + [ls], FILE_FORMAT.MOVE.value)

            kml = toKML(cleanFeatures(move_points))
            filename = os.path.join(basename + FILE_FORMAT.MOVE.value + ".kml")
            with open(filename, "w") as fp:
                fp.write(kml)
                logger.debug(f"saved kml {filename} ({len(move_points)})")

        # saveMe(self.taxipos, "4-taxi")
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

    def vnav(self):
        """
        Perform vertical navigation for route
        @todo: Add optional hold
        """
        is_grounded = True

        def fpi(f) -> int:
            return int(f.getProp(FEATPROP.FLIGHT_PLAN_INDEX))

        def respect250kn(speed_in_ms, alt_in_ft, switch_alt_in_ft: int = 10000) -> float:
            """Returns authorized speed in m/s"""
            return min(toMs(toKmh(kn=250)), speed_in_ms) if alt_in_ft < switch_alt_in_ft else speed_in_ms

        def transfer_restriction(src, dst):
            if src in self.flight.flightplan_wpts:
                r = src.getProp(FEATPROP.RESTRICTION)
                if r is not None and r.strip() != "":
                    dst.setProp(FEATPROP.RESTRICTION, r)
                    logger.debug(f"{src.getId()}: transferred restriction {r}")

        def addCurrentpoint(coll, pos, oi, ni, color, mark, reverse: bool = False):
            # catch up adding all points in flight plan between oi, ni
            # then add pos (which is between ni and ni+1)
            # logger.debug("%d %d %s" % (oi, ni, reverse))
            if oi != ni:
                for idx in range(oi + 1, ni + 1):
                    i = idx if not reverse else len(self.flight.flightplan_wpts) - idx - 1
                    wpt = self.flight.flightplan_wpts[i]
                    p = MovePoint.new(wpt)
                    logger.debug(
                        f"addCurrentpoint:{'(rev)' if reverse else ''} adding {p.getProp(FEATPROP.PLAN_SEGMENT_TYPE)} {p.getProp(FEATPROP.PLAN_SEGMENT_NAME)} ({fpi(p)})"
                    )
                    transfer_restriction(wpt, p)
                    p.setColor(color)
                    p.setMark(mark)
                    p.setProp(FEATPROP.FLIGHT_PLAN_INDEX, i)
                    p.setColor(POSITION_COLOR.FLIGHT_PLAN.value)  # remarkable point in GREEN
                    coll.append(p)
            coll.append(pos)
            # logger.debug("adding remarkable point: %s (%d)" % (pos.getProp(FEATPROP.MARK), len(coll)))
            # logger.debug("return index: %d" % (ni))
            # we now are at pos which is on LineString after index ni
            return ni

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
            return (newpos, addCurrentpoint(coll, newpos, fcidx, newidx, color, mark_tr, reverse))

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
            transfer_restriction(src, mvpt)
            arr.append(mvpt)
            return mvpt

        def climb_to_alt(
            start_idx, current_altitude, target_altitude, target_index, do_it: bool = True, expedite: bool = False, comment: str | None = None
        ) -> tuple[int, int]:
            """Compute distance necessary to reach target_altitude.
            From that distance, compute framing flight plan indices (example: between 6 and 7).
            Returns the last index (7). At index 7, we will be at target_altitude.

            Climbs from current_position at current_altitude to new position at target altitude.
            if expedite climb, climb first to target_altitude and then fly level to waypoint
            if not expedite, climb at regular pace to target_altitude at waypoint

            returns:
             - New position, which is a way point with restriction or top of climb
             - New altitude at waypoint (after climbing)
            """

            if target_altitude < current_altitude:
                logger.debug("climb to alt: need to descend")
                return descend_to_alt(start_idx, current_altitude, target_altitude, target_index, do_it, expedite)

            if target_altitude == current_altitude:
                logger.debug("same altitude, no need to climb")
                return (target_index, target_altitude)

            delta = target_altitude - current_altitude
            # ranges are initial-climb, climb-150, climb-240, climb-cruise
            # we assume we are above initial climb, we can also safely assure
            # that we are below FL150 for SID and STAR, but let's check it
            if self.flight.aircraft.actype.getClimbSpeedRangeForAlt(current_altitude) != self.flight.aircraft.actype.getClimbSpeedRangeForAlt(target_altitude):
                logger.warning(f"change of ranges for altitudes {current_altitude} -> {target_altitude}")

            roc = self.flight.aircraft.actype.getROCDistanceForAlt(
                toMeter(target_altitude if do_it else current_altitude)
            )  # special when we suspect we climb to cruise
            min_dist_to_climb = (toMeter(ft=delta) / roc) / 1000  # km
            logger.debug(f"need distance {round(min_dist_to_climb, 2)} km to climb")
            total_dist = 0
            curridx = start_idx
            while total_dist < min_dist_to_climb and curridx < (len(fc) - 1):
                d = distance(fc[curridx], fc[curridx + 1])
                total_dist = total_dist + d
                curridx = curridx + 1
                # print(">>>", curridx, d, total_dist)

            logger.debug(f"can climb from {current_altitude} at idx {start_idx} to {target_altitude} before idx {curridx} (at {round(total_dist, 2)} km)")

            if not do_it:
                logger.debug(f"just getting index for climb from {current_altitude} to {target_altitude}, no altitude change")
                return (curridx, target_altitude)

            # we are now at fc[curridx], at altitude target_altitude, two ways to get there
            if curridx > target_index:  # this means there will be a Restriction violation
                logger.warning(f"cannot climb {delta}ft before requested index {target_index}")
                logger.warning(f"restriction violation")

            if expedite:
                logger.debug(f"expedite: will climb from {current_altitude} at idx {start_idx} to {target_altitude} at idx {curridx}")
            else:  # regular gradient climb
                logger.debug(
                    f"no expedite: will climb from {current_altitude} at idx {start_idx} to {target_altitude} at idx {curridx}, (has {round(d, 2)} km to climb)"
                )
                curridx = max(curridx, target_index)
                currpos = None
                currdist = 0
                for idx in range(start_idx, curridx):
                    curralt = current_altitude + delta * (currdist / total_dist)
                    logger.debug(f"no expedite: at idx {idx}, alt={curralt}")
                    currpos = addMovepoint(
                        arr=self._premoves,
                        src=fc[idx],
                        alt=toMeter(ft=curralt),
                        speed=respect250kn(actype.getSI(ACPERF.climbFL150_speed), curralt),
                        vspeed=actype.getSI(ACPERF.climbFL150_vspeed),
                        color=POSITION_COLOR.CLIMB.value,
                        mark=FLIGHT_PHASE.CLIMB.value,
                        ix=idx,
                    )
                    if comment is not None:
                        currpos.setComment(comment)
                    d = distance(fc[idx], fc[idx + 1])
                    total_dist = total_dist + d
                    # print(">>>", cidx, d, total_dist)
                # for fun
                # d = reduce(distance, fc[start_idx:curridx], 0.0)

            return (curridx, target_altitude)

        def descend_to_alt(start_idx, current_altitude, target_altitude, target_index, do_it: bool = True, expedite: bool = False) -> tuple[int, int]:
            """Compute distance necessary to reach target_altitude.
            From that distance, compute framing flight plan indices (example: between 6 and 7).
            Returns the last index (7). At index 7, we will be at target_altitude.
            """

            MAX_TOD = 100  # km from airport

            if target_altitude > current_altitude:
                logger.debug("descend to alt: need to climb")
                return climb_to_alt(start_idx, current_altitude, target_altitude, target_index, do_it, expedite)

            if target_altitude == current_altitude:
                logger.debug("already at target altitude, no descend needed")
                return (target_index, target_altitude)

            delta = current_altitude - target_altitude

            if self.flight.aircraft.actype.getDescendSpeedRangeForAlt(current_altitude) != self.flight.aircraft.actype.getDescendSpeedRangeForAlt(
                target_altitude
            ):
                logger.warning(f"change of ranges for altitudes {current_altitude} -> {target_altitude}")

            rod = self.flight.aircraft.actype.getRODDistanceForAlt(toMeter(current_altitude))  # we descend as fast as current altitude allows it
            min_dist_to_descend = (toMeter(ft=delta) / rod) / 1000  # km
            # logger.debug(f"ROD {rod} at {current_altitude}, need distance {round(min_dist_to_descend, 2)} km to descend")
            if min_dist_to_descend > MAX_TOD:
                new_rod = toMeter(delta) / (MAX_TOD * 1000)
                min_dist_to_descend = MAX_TOD
                speed, vspeed = self.flight.aircraft.actype.getDescendSpeedAndVSpeedForAlt(toMeter(current_altitude))
                fpm = toFPM(ms=vspeed * new_rod / rod)
                logger.debug(
                    f"descend too long ({round(min_dist_to_descend, 2)} km), will expedite to max {round(toNm(m=MAX_TOD), 0)}nm (ROD={round(new_rod,2)}, or {round(fpm, 0)}ft/min)"
                )

            total_dist = 0
            curridx = target_index
            while total_dist < min_dist_to_descend and curridx > 0:
                d = distance(fc[curridx - 1], fc[curridx])
                total_dist = total_dist + d
                curridx = curridx - 1
                # print(">>>", curridx, d, total_dist)

            logger.debug(f"can descend from {current_altitude} at idx {curridx} to {target_altitude} at idx {target_index} (at {round(total_dist, 2)} km)")

            if not do_it:
                logger.debug(f"just getting index for descend from {current_altitude} to {target_altitude}, no altitude change")
                return (curridx, target_altitude)

            # we are now at fc[curridx], at altitude target_altitude, two ways to get there
            if curridx > start_idx:  # this means there will be a Restriction violation
                logger.warning(f"cannot descend {delta}ft from {curridx} before requested index {target_index}")
                logger.warning(f"restriction violation")

            if expedite:  # or min_dist_to_descend > ~ 100NM
                logger.debug(f"expedite: will descend from {current_altitude} at idx {start_idx} to {target_altitude} at idx {curridx}")
            else:  # regular gradient climb
                curridx = min(curridx, target_index)
                # for fun
                # d = reduce(distance, fc[start_idx:curridx], 0.0)
                d = 0
                for i in range(curridx, target_index):
                    d = d + distance(fc[i - 1], fc[i])
                logger.debug(
                    f"no expedite: will descend from {current_altitude} at idx {curridx} to {target_altitude} at idx {target_index}, (has {round(d, 2)} km to descend)"
                )

            return (target_index, target_altitude)

        # ###########################################################################################
        #
        #
        if self.flight.flightplan_wpts is None or len(self.flight.flightplan_wpts) == 0:
            logger.warning("no flight plan")
            return (False, "Movement::vnav no flight plan, cannot move")

        fc = self.flight.flightplan_wpts
        ac = self.flight.aircraft
        actype = ac.actype
        # actype.perfs()
        logger.debug(f"{'*' * 30} {type(self).__name__}: {len(fc)} points in flight plan {'*' * 30}")

        # for f in self.flight.flightplan_wpts:
        #     logger.debug("flight plan: %s" % (f.getProp(FEATPROP.PLAN_SEGMENT_TYPE)))

        # PART 1: FORWARD: From takeoff to top of ascent
        #
        #
        logger.debug(f"departure from {self.flight.departure.icao} " + "=" * 30)
        TOH_BLASTOFF = 0.2  # km, distance of take-off hold position from runway threshold
        groundmv = 0
        fcidx = 0
        rwy = None

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
                alt = 0

            brg = bearing(rwy_threshold, rwy.end.getPoint())
            takeoff_hold = destination(rwy_threshold, TOH_BLASTOFF, brg)
            logger.debug(f"departure from {rwy.name}, {brg:f}")

            p = addMovepoint(
                arr=self._premoves,
                src=takeoff_hold,
                alt=alt,
                speed=0,
                vspeed=0,
                color=POSITION_COLOR.TAKE_OFF_HOLD.value,
                mark=FLIGHT_PHASE.TAKE_OFF_HOLD.value,
                ix=0,
            )
            self.takeoff_hold = copy.deepcopy(p)  # we keep this special position for taxiing (end_of_taxi)
            logger.debug(f"takeoff hold at {rwy.name}, {TOH_BLASTOFF:f}")

            takeoff_distance = actype.getSI(ACPERF.takeoff_distance) * self.airport.runwayIsWet() / 1000  # must be km for destination()
            takeoff = destination(takeoff_hold, takeoff_distance, brg)

            p = addMovepoint(
                arr=self._premoves,
                src=takeoff,
                alt=alt,
                speed=actype.getSI(ACPERF.takeoff_speed),
                vspeed=actype.getSI(ACPERF.initial_climb_vspeed),
                color=POSITION_COLOR.TAKE_OFF.value,
                mark=FLIGHT_PHASE.TAKE_OFF.value,
                ix=0,
            )
            groundmv = takeoff_distance
            logger.debug(f"takeoff at {rwy.name}, {takeoff_distance:f}")

            self.addMessage(
                FlightMessage(
                    subject=f"ACARS: {self.flight.aircraft.icao24} {FLIGHT_PHASE.TAKE_OFF.value} from {self.flight.departure.icao}",
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
            logger.debug("initialClimb")
            step = actype.initialClimb(alt)  # (t, d, altend)
            initial_climb_distance = step[1] / 1000  # km
            # find initial climb point

            # we climb on path to see if we reach indices...
            currpos, newidx = moveOn(fc, fcidx, p, initial_climb_distance)
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
            logger.debug(f"initial climb end at index {newidx}, {round(initial_climb_distance,3)}km")
            # small control to see if next point on flight plan is AFTER end of initial climb
            ctrd = distance(fc[newidx], fc[newidx + 1])
            if initial_climb_distance > ctrd:
                logger.warning(f"initial climb finishes after start of SID at {round(ctrd,3)}km")
            else:
                logger.debug(f"index {newidx + 1} at {round(ctrd,3)}km")
            groundmv = groundmv + initial_climb_distance
            # we ignore vertices between takeoff and initial_climb
            # we go in straight line and ignore self._premoves, skipping eventual points
            fcidx = newidx

        else:  # no runway, simpler departure
            deptapt = fc[0]
            alt = deptapt.altitude()
            if alt is None:
                logger.warning(f"departure airport has no altitude: {deptapt}")
                alt = 0
            currpos = addMovepoint(
                arr=self._premoves,
                src=deptapt,
                alt=alt,
                speed=actype.getSI(ACPERF.takeoff_speed),
                vspeed=actype.getSI(ACPERF.initial_climb_vspeed),
                color=POSITION_COLOR.TAKE_OFF.value,
                mark=FLIGHT_PHASE.TAKE_OFF.value,
                ix=fcidx,
            )
            logger.debug("origin added first point")

            self.addMessage(
                FlightMessage(
                    subject=f"ACARS: {self.flight.aircraft.icao24} {FLIGHT_PHASE.TAKE_OFF.value} from {self.flight.departure.icao}",
                    flight=self,
                    sync=FLIGHT_PHASE.TAKE_OFF.value,
                    info=self.getInfo(),
                )
            )
            is_grounded = False

            # initial climb, commonly accepted to above 1500ft AGL
            logger.debug("initialClimb")
            step = actype.initialClimb(alt)  # (t, d, altend)
            # find initial climb point
            groundmv = step[1]

            currpos, fcidx = moveOnLS(
                coll=self._premoves,
                reverse=False,
                fc=fc,
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

        # ########################################################################################
        #
        # New algorithm to climb from initial climb altitude to cruise altitude while respecting alt contraints.
        #
        #
        if self.flight.departure.has_sids():
            logger.debug(f"--------------- climbing with constraints.. (SID = {self.flight.procedures.get(FLIGHT_SEGMENT.SID.value).name})")

            curralt = 1500.0  # ft
            curridx = fcidx  # we use curridx inside this if/then/else, we'll set fcidx back after this processing

            # Step 1: We are climbing... where is the next alt constraint we have to climb above?
            #
            # Note: this procedure just check for alt constraints.
            # Now is the aircraft capable of climing that fast? That is handled in climb_to_alt().
            # If not, climb_to_alt() will report a potential constraint violation.
            MAX_RESTRICTION_COUNT = 5
            LOOK_AHEAD_DISTANCE = 200  # km
            r = self.flight.next_above_alt_restriction(curridx, max_distance=LOOK_AHEAD_DISTANCE)
            above_restrictions = 0
            while r is not None and above_restrictions < MAX_RESTRICTION_COUNT:
                above_restrictions = above_restrictions + 1
                restricted_above_alt = r.alt2 if r.alt_restriction_type in ["B"] else r.alt1
                logger.debug(f"at index {curridx}, next restriction ABOVE at idx={fpi(r)} {r.getRestrictionDesc()}")
                r2 = self.flight.next_below_alt_restriction(curridx, fpi(r))

                # Step 1b : While climbing there, are there any constraints we have to stay below?
                below_restrictions = 0
                while r2 is not None and below_restrictions < MAX_RESTRICTION_COUNT:
                    # r2.alt1 is "below" limit in all cases
                    below_restrictions = below_restrictions + 1
                    restricted_below_alt = r2.alt1
                    logger.debug(f"at index {curridx}, next restriction BELOW at idx={fpi(r2)} {r2.getRestrictionDesc()}, will climb at {restricted_below_alt}")
                    tidx = fpi(r2)
                    curridx, curralt = climb_to_alt(
                        start_idx=curridx, current_altitude=curralt, target_altitude=restricted_below_alt, target_index=tidx, comment="remain below restriction"
                    )
                    logger.debug(f"now at altitude {curralt}, checking for next BELOW restriction")
                    r2 = self.flight.next_below_alt_restriction(curridx, fpi(r2))

                # Step 1c: Resume climbing to constraint to climb above...
                if curralt < restricted_above_alt:
                    logger.debug(f"at index {curridx}, no more BELOW restrictions, will climb to {restricted_above_alt}")
                    tidx = fpi(r)
                    curridx, curralt = climb_to_alt(
                        start_idx=curridx, current_altitude=curralt, target_altitude=restricted_above_alt, target_index=tidx, comment="climb above restriction"
                    )
                    # Step 1d: Is there a new alt constraint we have to climb above...
                    logger.debug(f"now at altitude {curralt}, checking for next ABOVE restrictions")
                else:
                    logger.debug(f"now at altitude {curralt} already at or above next ABOVE restriction ({restricted_above_alt})")
                r = self.flight.next_above_alt_restriction(curridx, max_distance=LOOK_AHEAD_DISTANCE)

            logger.debug(f"now at altitude {curralt} (after {above_restrictions} ABOVE restrictions, no more ABOVE restriction)")

            # Step 2: No more constraints to climb above, but while climbing to cruise alt, are there any constraints we have to stay below?
            cruise_alt = self.flight.flight_level * 100  # Target alt for climb, should actually be last alt for SID
            logger.debug(f"at index {curridx}, attempting to climb to cruise alt {cruise_alt}, checking for BELOW restrictions")
            idx_to_cruise_alt, dummy = climb_to_alt(start_idx=curridx, current_altitude=curralt, target_altitude=cruise_alt, target_index=None, do_it=False)
            r3 = self.flight.next_below_alt_restriction(curridx, idx_to_cruise_alt)
            below_restrictions = 0
            while r3 is not None and below_restrictions < MAX_RESTRICTION_COUNT:
                below_restrictions = below_restrictions + 1
                restricted_below_alt = r3.alt1
                logger.debug(f"at index {curridx}, next restriction BELOW at {fpi(r3)} {r3.getRestrictionDesc()}, will climb at {restricted_below_alt}")
                tidx = fpi(r3)
                curridx, curralt = climb_to_alt(
                    start_idx=curridx, current_altitude=curralt, target_altitude=restricted_below_alt, target_index=tidx, comment="remain below restriction"
                )
                # we now have to reevaluate when we will reach cruise alt...
                # curralt will temporarily be cruise alt, but if new r3 is not None, curralt will fall back to new restricted_below_alt
                r3 = self.flight.next_below_alt_restriction(curridx, idx_to_cruise_alt)

            logger.debug(f"at index {curridx} at altitude {curralt}, no more BELOW restriction, will now climb to {cruise_alt} with no restriction")
            logger.debug(f"--------------- ..done climbing with constraints")

            if curralt > 10000:
                logger.debug(f"note: restricted climb finishes above FL100")
            if curralt > cruise_alt:
                logger.warning(f"note: restricted climb finishes above cruise altitude")

            # "transition" :-) to former algorithm
            # Note: From previous algorithm, without contrains, rather than picking up from end of initial clim at 1500FT AGL,
            #       we are now at current alt a few indices later... nothing else differs.
            #       Resuming climb unconstrained to "cruise alt", from curralt rather than end_of_initial_climb.
            fcidx = curridx
            last_restricted_point = fc[curridx]
            currpos = addMovepoint(
                arr=self._premoves,
                src=last_restricted_point,
                alt=toMeter(ft=curralt),
                speed=respect250kn(actype.getSI(ACPERF.climbFL150_speed), curralt),
                vspeed=actype.getSI(ACPERF.climbFL150_vspeed),
                color=POSITION_COLOR.CLIMB.value,
                mark=FLIGHT_PHASE.END_DEPARTURE_RESTRICTIONS.value,
                ix=fcidx,
            )
            currpos.setComment("last point of restricted climb")

            logger.debug(f"resume climb from {self._premoves[-1].altitude()} with no restriction to cruise altitude")
        else:
            logger.debug(f"no SID, no restriction, climb to cruise altitude according to aicraft capabilities")

        #
        #
        # ########################################################################################

        # we have an issue if first point of SID is between TAKE_OFF and END_OF_INITIAL_CLIMB (which is )
        # but it is very unlikely (buy it may happen, in which case the solution is to remove the first point if SID)
        # Example of issue: BEY-DOH //DEP OLBA RW34 SID LEBO2F //ARR OTHH
        if self._premoves[-1].altitude() < toMeter(10000):
            logger.debug("climbToFL100")
            step = actype.climbToFL100(currpos.altitude())  # (t, d, altend)
            groundmv = groundmv + step[1]
            currpos, fcidx = moveOnLS(
                coll=self._premoves,
                reverse=False,
                fc=fc,
                fcidx=fcidx,
                currpos=currpos,
                dist=step[1],
                alt=step[2],
                speed=min(actype.fl100Speed(), actype.getSI(ACPERF.climbFL150_speed)),
                vspeed=actype.getSI(ACPERF.climbFL150_vspeed),
                color=POSITION_COLOR.CLIMB.value,
                mark="end_fl100_climb",
                mark_tr=FLIGHT_PHASE.CLIMB.value,
            )

        # climb to cruise altitude
        cruise_speed = actype.getSI(ACPERF.cruise_mach)

        if self._premoves[-1].altitude() <= toMeter(15000) and self.flight.flight_level > 150:
            logger.debug("climbToFL150")
            step = actype.climbToFL150(currpos.altitude())  # (t, d, altend)
            groundmv = groundmv + step[1]
            currpos, fcidx = moveOnLS(
                coll=self._premoves,
                reverse=False,
                fc=fc,
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

            if self._premoves[-1].altitude() <= toMeter(24000) and self.flight.flight_level > 240:
                logger.debug("climbToFL240")
                step = actype.climbToFL240(currpos.altitude())  # (t, d, altend)
                groundmv = groundmv + step[1]
                currpos, fcidx = moveOnLS(
                    coll=self._premoves,
                    reverse=False,
                    fc=fc,
                    fcidx=fcidx,
                    currpos=currpos,
                    dist=step[1],
                    alt=step[2],
                    speed=actype.getSI(ACPERF.climbFL240_speed),
                    vspeed=actype.getSI(ACPERF.climbFL240_vspeed),
                    color=POSITION_COLOR.CLIMB.value,
                    mark="end_fl240_climb",
                    mark_tr=FLIGHT_PHASE.CLIMB.value,
                )

                if self._premoves[-1].altitude() <= toMeter(24000) and self.flight.flight_level > 240:
                    logger.debug("climbToCruise")
                    step = actype.climbToCruise(currpos.altitude(), self.flight.getCruiseAltitude())  # (t, d, altend)
                    groundmv = groundmv + step[1]
                    currpos, fcidx = moveOnLS(
                        coll=self._premoves,
                        reverse=False,
                        fc=fc,
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
                    fc=fc,
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
                fc=fc,
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
            fc=fc,
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
        logger.debug("cruise at %d after %f" % (top_of_ascent_idx, groundmv))
        logger.debug(f"ascent added (+{len(self._premoves)} {len(self._premoves)})")
        # cruise until top of descent
        #
        # PART 2: REVERSE: From brake on runway (end of roll out) to top of descent
        #
        #
        logger.debug(f"arrival to {self.flight.arrival.icao} " + "=" * 30)

        # Set a few default sensible values in case procedures do not give any
        # STAR
        STAR_ALT = 6000 * FT  # Altitude ABG at which we perform STAR path before approach
        starproc = self.flight.procedures.get(FLIGHT_SEGMENT.STAR.value)
        if starproc is not None:
            dummy, STAR_ALT = starproc.getEntrySpeedAndAlt()

        # APPROACH
        FINAL_FIX_ALT = 2000 * FT  # Altitude ABG at which we start final, always straight line aligned with runway
        APPROACH_ALT = 3000 * FT  # Altitude ABG at which we perform approach path before final
        FINAL_VSPEED = None

        # 1. Try to get from procedure
        apchproc = self.flight.procedures.get(FLIGHT_SEGMENT.APPCH.value)
        if starproc is not None:
            dummy, APPROACH_ALT = apchproc.getEntrySpeedAndAlt()
            FINAL_VSPEED, FINAL_FIX_ALT = apchproc.getExitSpeedAndAlt()
            logger.debug(f"final vspeed from approach procedure ({FINAL_VSPEED})")

        # 2. Try from landing speed
        if FINAL_VSPEED is None or FINAL_VSPEED == 0:
            if actype.getSI(ACPERF.landing_speed) is not None and actype.getSI(ACPERF.landing_speed) > 0:
                # Alternative 2 : VSPEED adjusted to have an angle/ratio of 3% (common)
                # Note: Landing speed is in kn. 1 kn = 101.26859 ft/min :-)
                FINAL_VSPEED = 0.03 * actype.get(ACPERF.landing_speed) * 101.26859  # in ft/min
                logger.debug(f"final vspeed from 3% landing speed ({FINAL_VSPEED})")

        # 3. Use sensible default
        if FINAL_VSPEED is None or FINAL_VSPEED == 0:
            FINAL_VSPEED = 600  # ft/min, fairly standard
            logger.debug(f"final vspeed from default ({FINAL_VSPEED})")

        FINAL_FIX_ALT = round(FINAL_FIX_ALT, 1)
        APPROACH_ALT = round(APPROACH_ALT, 1)
        final_vspeed_ms = FINAL_VSPEED * FT / 60  # in meters/sec
        logger.debug(f"final vspeed {actype.typeId}: {round(final_vspeed_ms, 2)} m/s, {round(FINAL_VSPEED, 2)} ft/min")

        # LANDING AND TOUCH DOWN
        LAND_TOUCH_DOWN = 0.4  # km, distance of touch down from the runway threshold (given in CIFP)

        revmoves = []
        groundmv = 0
        fc = self.flight.flightplan_wpts.copy()
        fc.reverse()
        fcidx = 0

        is_grounded = True

        if self.flight.arrival.has_rwys():  # the path starts at the of roll out
            if self.flight.is_arrival():  # we are at the managed airport, we must use the selected runway
                rwy = self.flight.rwy
            else:
                rwy = self.flight.arrival.selectRWY(self.flight)
                logger.debug(f"remote arrival: using runway {rwy.name}")

            rwy_threshold = rwy.getPoint()
            alt = rwy_threshold.altitude()
            if alt is None:
                logger.warning(f"(rev) departure airport has no altitude: {rwy_threshold}")
                alt = 0

            brg = bearing(rwy_threshold, rwy.end.getPoint())
            touch_down = destination(rwy_threshold, LAND_TOUCH_DOWN, brg)
            logger.debug(f"(rev) arrival runway {rwy.name}, {brg:f}")

            # First point is end off roll out, read to exit the runway and taxi
            rollout_distance = actype.getSI(ACPERF.landing_distance) * self.airport.runwayIsWet() / 1000  # must be km for destination()
            end_rollout = destination(touch_down, rollout_distance, brg)

            currpos = addMovepoint(
                arr=revmoves,
                src=end_rollout,
                alt=alt,
                speed=TAXI_SPEED,
                vspeed=0,
                color=POSITION_COLOR.ROLL_OUT.value,
                mark=FLIGHT_PHASE.END_ROLLOUT.value,
                ix=len(fc) - fcidx,
            )
            logger.debug(f"(rev) end roll out at {rwy.name}, {rollout_distance:f}, {alt:f}")
            self.end_rollout = copy.deepcopy(currpos)  # we keep this special position for taxiing (start_of_taxi)

            # Point just before is touch down
            p = addMovepoint(
                arr=revmoves,
                src=touch_down,
                alt=alt,
                speed=actype.getSI(ACPERF.landing_speed),
                vspeed=0,
                color=POSITION_COLOR.TOUCH_DOWN.value,
                mark=FLIGHT_PHASE.TOUCH_DOWN.value,
                ix=len(fc) - fcidx,
            )
            logger.debug(f"(rev) touch down at {rwy.name}, {LAND_TOUCH_DOWN:f}, {alt:f}")

            self.addMessage(
                FlightMessage(
                    subject=f"ACARS: {self.flight.aircraft.icao24} {FLIGHT_PHASE.TOUCH_DOWN.value} at {self.flight.arrival.icao}",
                    flight=self,
                    sync=FLIGHT_PHASE.TOUCH_DOWN.value,
                    info=self.getInfo(),
                )
            )
            is_grounded = False

            # we move to the final fix at max FINAL_FIX_ALT ft, landing speed, FINAL_VSPEED (ft/min), from touchdown
            logger.debug("(rev) final")
            step = actype.descentFinal(alt, final_vspeed_ms, safealt=FINAL_FIX_ALT)  # (t, d, altend)
            final_distance = step[1] / 1000  # km
            # find final fix point

            # we (reverse) descent on path to see if we reach indices...
            p, newidx = moveOn(fc, fcidx, p, final_distance)

            # we ignore currpos for now, we will descent straight, we ignore points
            # between fcidx and newidx during final descent...
            final_fix = destination(touch_down, final_distance, brg + 180)

            currpos = addMovepoint(
                arr=revmoves,
                src=final_fix,
                alt=alt + FINAL_FIX_ALT,
                speed=actype.getSI(ACPERF.landing_speed),
                vspeed=final_vspeed_ms,
                color=POSITION_COLOR.FINAL.value,
                mark=FLIGHT_PHASE.FINAL_FIX.value,
                ix=newidx,
            )
            logger.debug("(rev) final fix at new=%d(old=%d), %f" % (newidx, fcidx, final_distance))
            groundmv = groundmv + final_distance
            # we ignore vertices between takeoff and initial_climb
            # we go in straight line and ignore self._premoves, skipping eventual points
            fcidx = newidx

            # we are at final fix
            groundmv = groundmv + step[1]
            # transition (direct) from approach alt (initial fix) to final fix alt
            currpos, fcidx = moveOnLS(
                coll=revmoves,
                reverse=True,
                fc=fc,
                fcidx=fcidx,
                currpos=currpos,
                dist=step[1],
                alt=alt + APPROACH_ALT,
                speed=actype.getSI(ACPERF.landing_speed),
                vspeed=actype.getSI(ACPERF.approach_vspeed),
                color=POSITION_COLOR.FINAL.value,
                mark="if_to_ff",
                mark_tr=FLIGHT_PHASE.FINAL.value,
            )
        else:
            arrvapt = fc[fcidx]
            alt = arrvapt.altitude()
            if alt is None:
                logger.warning(f"(rev) arrival airport has no altitude: {arrvapt}")
                alt = 0

            currpos = addMovepoint(
                arr=revmoves,
                src=arrvapt,
                alt=alt,
                speed=actype.getSI(ACPERF.landing_speed),
                vspeed=final_vspeed_ms,
                color=POSITION_COLOR.DESTINATION.value,
                mark="destination",
                ix=len(fc) - fcidx,
            )
            logger.debug("(rev) destination added as last point")

            self.addMessage(
                FlightMessage(
                    subject=f"ACARS: {self.flight.aircraft.icao24} {FLIGHT_PHASE.TOUCH_DOWN.value} at {self.flight.arrival.icao}",
                    flight=self,
                    sync=FLIGHT_PHASE.TOUCH_DOWN.value,
                    info=self.getInfo(),
                )
            )
            is_grounded = False

            # we move to the final fix at max 3000ft, approach speed from airport last point, vspeed=FINAL_VSPEED
            logger.debug("(rev) final")
            step = actype.descentFinal(alt, final_vspeed_ms, safealt=FINAL_FIX_ALT)  # (t, d, altend)
            groundmv = groundmv + step[1]
            # find final fix point
            currpos, fcidx = moveOnLS(
                coll=revmoves,
                reverse=True,
                fc=fc,
                fcidx=fcidx,
                currpos=currpos,
                dist=step[1],
                alt=alt + APPROACH_ALT,
                speed=actype.getSI(ACPERF.landing_speed),
                vspeed=final_vspeed_ms,
                color=POSITION_COLOR.FINAL.value,
                mark="start_of_final",
                mark_tr=FLIGHT_PHASE.FINAL.value,
            )

        # ########################################################################################
        #
        # New algorithm to descend from cruise altitude to final fix while respecting alt contraints.
        #
        #
        if self.flight.arrival.has_stars() or self.flight.arrival.has_approaches():
            logger.debug(f"--------------- descending with constraints..")
            if self.flight.arrival.has_stars():
                logger.debug(f"STAR = {self.flight.procedures.get(FLIGHT_SEGMENT.STAR.value).name}")
            if self.flight.arrival.has_approaches():
                logger.debug(f"APPCH = {self.flight.procedures.get(FLIGHT_SEGMENT.APPCH.value).name}")

            cruise_start_idx, curridx = self.flight.phase_indices(phase=FLIGHT_SEGMENT.CRUISE)
            if curridx == None:
                logger.debug(f"cannot find end of cruise")
            else:
                logger.debug(f"cruise finishes at {curridx}")

            # Step 1: While descending, are there restriction we have to fly BELOW (i.e. expedite descend)
            MAX_RESTRICTION_COUNT = 5
            LOOK_AHEAD_DISTANCE = 250  # km
            curralt = self.flight.flight_level * 100  # ft
            r = self.flight.next_below_alt_restriction2(curridx, max_distance=LOOK_AHEAD_DISTANCE)  # km
            below_restrictions = 0
            while r is not None and below_restrictions < MAX_RESTRICTION_COUNT:
                below_restrictions = below_restrictions + 1
                logger.debug(f"at index {curridx} at {curralt}, next restriction BELOW at idx={fpi(r)} {r.getRestrictionDesc()}")

                # when should we start to descend to satisfy this?
                candidate_alt = r.alt1
                start_idx, dummy = descend_to_alt(start_idx=curridx, current_altitude=curralt, target_altitude=candidate_alt, target_index=fpi(r), do_it=False)
                logger.debug(f"must start descend from {curralt} at {start_idx} to satisfy restriction BELOW at idx={fpi(r)} {r.getRestrictionDesc()}")

                curridx = fpi(r)
                # Step 1b: While descending there, are there restrictions we have to stay ABOVE (i.e. not descend too fast...)
                r2 = self.flight.next_above_alt_restriction2(start_idx, fpi(r))
                above_restrictions = 0
                while r2 is not None and above_restrictions < MAX_RESTRICTION_COUNT:
                    above_restrictions = above_restrictions + 1
                    restricted_above_alt = r2.alt2 if r2.alt_restriction_type in ["B"] else r2.alt1
                    if restricted_above_alt > candidate_alt:
                        logger.debug(
                            f"at index {curridx}, next restriction ABOVE at idx={fpi(r2)} {r2.getRestrictionDesc()}, will descend to {restricted_above_alt}"
                        )
                        tidx = fpi(r2)
                        curridx, curralt = descend_to_alt(start_idx=curridx, current_altitude=curralt, target_altitude=restricted_above_alt, target_index=tidx)
                        logger.debug(f"now at {above_restrictions} ABOVE restriction(s) at altitude {curralt}, checking for next ABOVE restriction")
                    else:
                        logger.debug(f"ABOVE restriction {r2.getRestrictionDesc()} at {fpi(r2)} satisfied")
                    r2 = self.flight.next_above_alt_restriction2(curridx, fpi(r2))

                # Step 1c: no more ABOVE restrictions we descend to satify Step 1
                if r.alt1 < curralt:
                    logger.debug(f"at index {curridx}, no more ABOVE restrictions, will decend to {r.alt1}")
                    tidx = fpi(r)
                    curridx, curralt = descend_to_alt(start_idx=curridx, current_altitude=curralt, target_altitude=r.alt1, target_index=tidx)
                    r = self.flight.next_below_alt_restriction2(curridx, max_distance=LOOK_AHEAD_DISTANCE)
                else:
                    logger.debug(f"already at {curralt}, lower than or equal to original BELOW restriction at {candidate_alt}, no need to descend")

                logger.debug(f"now at altitude {curralt}, checking for next BELOW restriction")

            logger.debug(f"now at altitude {curralt} (after {below_restrictions} BELOW restriction), no more BELOW restriction")

            finalfix_alt = 0  # Default target alt for descend ft
            logger.debug(f"at index {curridx}, attempting to descend to final fix alt {finalfix_alt}, checking for ABOVE restrictions")
            idx_to_finalfix_alt, dummy = descend_to_alt(
                start_idx=curridx, current_altitude=curralt, target_altitude=finalfix_alt, target_index=len(fc) - 1, do_it=False
            )
            logger.debug(f"index of final fix evaluated at {idx_to_finalfix_alt}")
            r3 = self.flight.next_above_alt_restriction2(curridx, idx_to_finalfix_alt)
            above_restrictions = 0
            while r3 is not None and above_restrictions < MAX_RESTRICTION_COUNT:
                above_restrictions = above_restrictions + 1
                restricted_above_alt = r3.alt2 if r3.alt_restriction_type in ["B"] else r3.alt1
                logger.debug(f"at index {curridx}, next restriction ABOVE at {fpi(r3)} {r3.getRestrictionDesc()}, will descend to {restricted_above_alt}")
                tidx = fpi(r3)
                curridx, curralt = descend_to_alt(start_idx=curridx, current_altitude=curralt, target_altitude=restricted_above_alt, target_index=tidx)
                # we now have to reevaluate when we will reach final fix alt...
                # curralt will temporarily be final fix alt, but if new r3 is not None, curralt will fall back to new r3.alt1
                idx_to_finalfix_alt, dummy = descend_to_alt(
                    start_idx=curridx, current_altitude=curralt, target_altitude=finalfix_alt, target_index=len(fc) - 1, do_it=False
                )
                logger.debug(f"index of final fix re-evaluated at {idx_to_finalfix_alt}")
                r3 = self.flight.next_above_alt_restriction2(curridx, idx_to_finalfix_alt)

            logger.debug(f"at index {curridx} at altitude {curralt}, no more ABOVE restrictions, will descend to {finalfix_alt} with no restriction")
            logger.debug(f"--------------- ..done descending with constraints")
            logger.debug(f"resume descend with no restriction to touch down")
            if curralt < 5000:
                logger.debug(f"note: restricted descend finishes above 5000ft")
        else:
            logger.debug(f"no STAR or APPROACH, no restriction, descend from cruise altitude according to aicraft capabilities")
        #
        #
        # ########################################################################################

        # if type(self).__name__ == "ArrivalMove":
        # find first point of approach:
        k = len(fc) - 1
        while fc[k].getProp(FEATPROP.PLAN_SEGMENT_TYPE) != "appch" and k > 0:
            k = k - 1
        if k == 0:
            logger.warning("no approach found")
        else:
            logger.debug("(rev) start of approach at index %d, %s" % (k, fc[k].getProp(FEATPROP.PLAN_SEGMENT_TYPE)))
            if k <= fcidx:
                logger.debug("(rev) final fix seems further away than start of apprach")
            else:
                logger.debug("(rev) flight level to final fix")
                # add all approach points between start to approach to final fix
                first = True  # we name last point of approach "initial fix"
                for i in range(fcidx + 1, k):
                    wpt = fc[i]
                    # logger.debug("APPCH: flight level: %d %s" % (i, wpt.getProp(FEATPROP.PLAN_SEGMENT_TYPE)))
                    p = addMovepoint(
                        arr=revmoves,
                        src=wpt,
                        alt=alt + APPROACH_ALT,
                        speed=actype.getSI(ACPERF.approach_speed),
                        vspeed=0,
                        color=POSITION_COLOR.APPROACH.value,
                        mark=(FLIGHT_PHASE.INITIAL_FIX.value if first else FLIGHT_PHASE.APPROACH.value),
                        ix=len(fc) - i,
                    )
                    first = False
                    # logger.debug("adding remarkable point: %d %s (%d)" % (i, p.getProp(FEATPROP.MARK), len(revmoves)))

                # add start of approach
                currpos = addMovepoint(
                    arr=revmoves,
                    src=fc[k],
                    alt=alt + APPROACH_ALT,
                    speed=actype.getSI(ACPERF.approach_speed),
                    vspeed=0,
                    color=POSITION_COLOR.APPROACH.value,
                    mark="start_of_approach",
                    ix=len(fc) - k,
                )
                # logger.debug("adding remarkable point: %d %s (%d)" % (k, currpos.getProp(FEATPROP.MARK), len(revmoves)))

                fcidx = k

        # find first point of star:
        k = len(fc) - 1
        while fc[k].getProp(FEATPROP.PLAN_SEGMENT_TYPE) != "star" and k > 0:
            k = k - 1
        if k == 0:
            logger.warning("(rev) no star found")
        else:
            logger.debug("(rev) start of star at index %d, %s" % (k, fc[k].getProp(FEATPROP.PLAN_SEGMENT_TYPE)))
            if k <= fcidx:
                logger.debug("(rev) final fix seems further away than start of star")
            else:
                logger.debug("(rev) flight level to start of approach")
                # add all approach points between start to approach to final fix
                for i in range(fcidx + 1, k):
                    wpt = fc[i]
                    # logger.debug("STAR: flight level: %d %s" % (i, wpt.getProp(FEATPROP.PLAN_SEGMENT_TYPE)))
                    p = addMovepoint(
                        arr=revmoves,
                        src=wpt,
                        alt=alt + STAR_ALT,
                        speed=actype.getSI(ACPERF.approach_speed),
                        vspeed=0,
                        color=POSITION_COLOR.APPROACH.value,
                        mark="star",
                        ix=len(fc) - i,
                    )

                    # logger.debug("adding remarkable point: %d %s (%d)" % (i, p.getProp(FEATPROP.MARK), len(revmoves)))
                # add start of approach
                currpos = addMovepoint(
                    arr=revmoves,
                    src=fc[k],
                    alt=alt + STAR_ALT,
                    speed=actype.getSI(ACPERF.approach_speed),
                    vspeed=0,
                    color=POSITION_COLOR.APPROACH.value,
                    mark="start_of_star",
                    ix=len(fc) - k,
                )
                # logger.debug("adding remarkable point: %d %s (%d)" % (k, currpos.getProp(FEATPROP.MARK), len(revmoves)))
                #
                # @todo: We assume start of star is where holding occurs
                self.holdingpoint = fc[k].id
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
                #         p.setAltitude(alt+STAR_ALT)
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

                fcidx = k

        if self.flight.flight_level > 100:
            # descent from FL100 to first approach point
            logger.debug("(rev) descent to star altitude")
            step = actype.descentApproach(10000 * FT, alt + STAR_ALT)  # (t, d, altend)
            groundmv = groundmv + step[1]
            currpos, fcidx = moveOnLS(
                coll=revmoves,
                reverse=True,
                fc=fc,
                fcidx=fcidx,
                currpos=currpos,
                dist=step[1],
                alt=10000 * FT,
                speed=actype.getSI(ACPERF.approach_speed),
                vspeed=actype.getSI(ACPERF.approach_vspeed),
                color=POSITION_COLOR.DESCEND.value,
                mark="descent_fl100_reached",
                mark_tr=FLIGHT_PHASE.DESCEND.value,
            )

            if self.flight.flight_level > 240:
                # descent from FL240 to FL100
                logger.debug("(rev) descent to FL100")
                step = actype.descentToFL100(24000 * FT)  # (t, d, altend)
                groundmv = groundmv + step[1]
                currpos, fcidx = moveOnLS(
                    coll=revmoves,
                    reverse=True,
                    fc=fc,
                    fcidx=fcidx,
                    currpos=currpos,
                    dist=step[1],
                    alt=24000 * FT,
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
                    currpos, fcidx = moveOnLS(
                        coll=revmoves,
                        reverse=True,
                        fc=fc,
                        fcidx=fcidx,
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
                currpos, fcidx = moveOnLS(
                    coll=revmoves,
                    reverse=True,
                    fc=fc,
                    fcidx=fcidx,
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
            step = actype.descentApproach(self.flight.getCruiseAltitude(), alt + APPROACH_ALT)  # (t, d, altend)
            groundmv = groundmv + step[1]
            currpos, fcidx = moveOnLS(
                coll=revmoves,
                reverse=True,
                fc=fc,
                fcidx=fcidx,
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
        currpos, fcidx = moveOnLS(
            coll=revmoves,
            reverse=True,
            fc=fc,
            fcidx=fcidx,
            currpos=currpos,
            dist=DECELERATION_DISTANCE,
            alt=self.flight.getCruiseAltitude(),
            speed=cruise_speed,
            vspeed=0,
            color=POSITION_COLOR.DECELERATE.value,
            mark=FLIGHT_PHASE.LEAVE_CRUISE_SPEED.value,
            mark_tr="end_of_leave_cruise_speed",
        )

        top_of_decent_idx = fcidx + 1  # we reach top of descent between idx and idx+1, so we cruise until idx+1
        logger.debug("(rev) reverse descent at %d after %f" % (top_of_decent_idx, groundmv))
        # we .reverse() array:
        top_of_decent_idx = len(self.flight.flightplan_wpts) - top_of_decent_idx - 1
        logger.debug("(rev) cruise until %d, descent after %d, remains %f to destination" % (top_of_decent_idx, top_of_decent_idx, groundmv))

        # PART 3: Join top of ascent to top of descent at cruise speed
        #
        # If airawys have restrictions, should adjust "stepped" climbs/desends
        # to comply with airway restrictions.
        #
        # We copy waypoints from start of cruise to end of cruise
        logger.debug("cruise")
        if top_of_decent_idx > top_of_ascent_idx:
            # logger.debug("adding cruise: %d -> %d" % (top_of_ascent_idx, top_of_decent_idx))
            for i in range(top_of_ascent_idx, top_of_decent_idx):
                wpt = self.flight.flightplan_wpts[i]
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

        # PART 4: Add descent and final
        #
        #
        revmoves.reverse()
        self._premoves = self._premoves + revmoves

        idx = 0
        for f in self._premoves:
            f.setProp(FEATPROP.PREMOVE_INDEX, idx)
            idx = idx + 1

        self._points = self._premoves  # for tabulate printing

        logger.debug(f"descent added (+{len(revmoves)} {len(self._premoves)})")
        # printFeatures(self._premoves, "holding")

        logger.debug("terminated " + "=" * 30)
        return (True, "Movement::vnav completed without restriction")

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
        last_speed = toMs(toKmh(kn=200))  # kn to km/h; and km/h to m/s

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

    def tabulateMovement2(self):
        def alt_ft(a):
            if a is None:
                return ""
            return str(round(a * FT))

        def speed_kn(a):
            if a is None:
                return ""
            return str(round(3.6 * a / NAUTICAL_MILE))

        def speed_fpm(a):
            if a is None:
                return ""
            return str(round(60 * a * FT))

        output = io.StringIO()
        print("\n", file=output)
        print(f"FLIGHT MOVEMENT", file=output)
        HEADER = [
            "INDEX",
            "SEGMENT TYPE",
            "SEGMENT NAME",
            "WAYPOINT",
            "RESTRICTIONS",
            "DISTANCE",
            "TOTAL DISTANCE",
            "ALT",
            "ALT (ft)",
            "SPEED",
            "SPEED (kn)",
            "V/S",
            "V/S (fp/m)",
            "Comments",
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
                if not r.checkSpeed(w):
                    speed_ok = " ***"
                if not r.checkAltitude(w.geometry):
                    alt_ok = " ***"

            table.append(
                [
                    idx,
                    w.getProp(FEATPROP.PLAN_SEGMENT_TYPE),
                    w.getProp(FEATPROP.PLAN_SEGMENT_NAME),
                    w.getId(),
                    restriction,
                    round(d, 1),
                    round(total_dist),
                    w.altitude(),
                    alt_ft(w.altitude()) + alt_ok,
                    w.speed(),
                    speed_kn(w.speed()) + speed_ok,
                    w.vspeed(),
                    speed_fpm(w.vspeed()),
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

    def add_tmo(self, TMO: float = 10 * NAUTICAL_MILE, mark: str = FLIGHT_PHASE.TEN_MILE_OUT.value):
        # We add a TMO point (Ten (nautical) Miles Out). Should be set before we interpolate.
        # TMO = 10 * NAUTICAL_MILE  # km
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
            logger.debug(f"added at ~{d:f} km, ~{d / NAUTICAL_MILE:f} nm from touch down (path is {prev:f} km, {prev/NAUTICAL_MILE:f} nm)")

            self.addMessage(FlightMessage(subject=f"{self.flight_id} {mark}", flight=self, sync=mark))
        else:
            logger.warning(f"less than {TMO} miles, no {mark} point added")

        return (True, "Movement::add_tmo added")

    def add_faraway(self, FARAWAY: float = 100 * NAUTICAL_MILE):
        # We add a FARAWAY point when flight is at FARAWAY from begin of roll (i.e. at FARAWAY from airport).
        # FARAWAY is ~100 miles away following airways (i.e. 100 miles of flight to go),
        # not in straght line, although we could adjust algorithm if needed.
        return self.add_tmo(TMO=FARAWAY, mark=FLIGHT_PHASE.FAR_AWAY.value)


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

        self.addMessage(
            FlightMessage(
                subject=f"ACARS: {self.flight.aircraft.icao24} {FLIGHT_PHASE.ONBLOCK.value} at {self.flight.ramp.getName()}",
                flight=self,
                sync=FLIGHT_PHASE.ONBLOCK.value,
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

        self.addMessage(
            FlightMessage(
                subject=f"ACARS: {self.flight.aircraft.icao24} {FLIGHT_PHASE.OFFBLOCK.value} from {self.flight.ramp.getName()}",
                flight=self,
                sync=FLIGHT_PHASE.OFFBLOCK.value,
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

        self.addMessage(
            FlightMessage(
                subject=f"ACARS: {self.flight.aircraft.icao24} {FLIGHT_PHASE.OFFBLOCK.value} from {self.flight.ramp.getName()}",
                flight=self,
                sync=FLIGHT_PHASE.OFFBLOCK.value,
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
