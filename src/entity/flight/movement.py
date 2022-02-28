"""
A succession of positions where the aircraft passes. Includes taxi and takeoff or landing and taxi.
"""
import os
import json
import logging
from math import pi
from typing import Union
import copy

from geojson import Point, LineString, FeatureCollection, Feature
from turfpy.measurement import distance, destination, bearing

from ..flight import Flight
from ..airspace import Restriction
from ..airport import AirportBase
from ..aircraft import ACPERF
from ..geo import FeatureWithProps, moveOn, cleanFeatures, printFeatures, findFeatures, asLineString, toKML
from ..graph import Route
from ..utils import FT, NAUTICAL_MILE
from ..constants import POSITION_COLOR, FEATPROP, TAKEOFF_QUEUE_SIZE, TAXI_SPEED, SLOW_SPEED
from ..constants import FLIGHT_DATABASE, FLIGHT_PHASE
from ..parameters import AODB_DIR

from .standardturn import standard_turn_flyby
from .interpolate import interpolate as doInterpolation, time as doTime

logger = logging.getLogger("Movement")


class MovePoint(FeatureWithProps):
    """
    A MovePoint is an application waypoint through which vehicle passes.
    It is a GeoJSON Feature<Point> with facilities to set a few standard
    properties like altitude, speed, vertical speed and properties.
    It can also set colors for geojson.io map display.
    Altitude is stored in third geometry coordinates array value.
    """
    def __init__(self, geometry: Union[Point, LineString], properties: dict):
        FeatureWithProps.__init__(self, geometry=geometry, properties=copy.deepcopy(properties))


class RestrictedMovePoint(MovePoint, Restriction):
    """
    A RestrictedMovePoint is a MovePoint with altitude and/or speed restrictions.
    """
    def __init__(self, geometry: Union[Point, LineString], properties: dict):
        MovePoint.__init__(self, geometry=geometry, properties=properties)
        Restriction.__init__(self)


class Movement:
    """
    Movement build the detailed path of the aircraft, both on the ground (taxi) and in the air,
    from takeoff to landing and roll out.
    """
    def __init__(self, flight: Flight, airport: AirportBase):
        self.flight = flight
        self.flight_id = self.flight.getId()
        self.airport = airport
        self.pauses = {}  # Dict of "variable" pauses that can be added to point: "pause-name": {Feature-properties-select}
        self.moves = []  # Array of Features<Point>
        self.moves_st = []  # Array of Features<Point>
        self.takeoff_hold = None
        self.end_rollout = None
        self.holdingpoint = None
        self.taxipos = []  # Array of Features<Point>


    @staticmethod
    def create(flight: Flight, airport: AirportBase):
        # Allows to expose Movement without exposing ArrivalMove or DepartureMove
        if flight.is_arrival():
            return ArrivalMove(flight, airport)
        return DepartureMove(flight, airport)


    def make(self):
        """
        Chains local function calls to do the work.
        """
        status = self.vnav()
        if not status[0]:
            logger.warning(status[1])
            return status

        status = self.standard_turns()
        if not status[0]:
            logger.warning(status[1])
            return status

        status = self.add_tmo()
        if not status[0]:
            logger.warning(status[1])
            return status

        status = self.interpolate()
        if not status[0]:
            logger.warning(status[1])
            return status

        status = self.time()
        if not status[0]:
            logger.warning(status[1])
            return status

        status = self.taxi()
        if not status[0]:
            logger.warning(status[1])
            return status

        status = self.taxiInterpolateAndTime()
        if not status[0]:
            logger.warning(status[1])
            return status
        # printFeatures(self.taxipos, "after taxi")

        return (True, "Movement::make completed")


    def save(self):
        """
        Save flight paths to 3 files for flight plan, detailed movement, and taxi path.
        Save a technical json file which can be loaded later, and GeoJSON files for display.
        @todo should save file format version number.
        """
        basename = os.path.join(AODB_DIR, FLIGHT_DATABASE, self.flight_id)

        def saveMe(arr, name):
            # filename = os.path.join(basename + "-" + name + ".json")
            # with open(filename, "w") as fp:
            #     json.dump(arr, fp, indent=4)

            filename = os.path.join(basename + "-" + name + ".geojson")
            with open(filename, "w") as fp:
                json.dump(FeatureCollection(features=cleanFeatures(arr)), fp, indent=4)

        saveMe(self.flight.flightplan_cp, "1-plan")
        ls = Feature(geometry=asLineString(self.flight.flightplan_cp))
        saveMe(self.flight.flightplan_cp + [ls], "1-plan_ls")

        saveMe(self.moves, "2-move")
        ls = Feature(geometry=asLineString(self.moves))
        saveMe(self.moves + [ls], "2-move_ls")

        saveMe(self.moves_st, "3-movest")
        ls = Feature(geometry=asLineString(self.moves_st))
        saveMe(self.moves_st + [ls], "3-movest_ls")

        saveMe(self.taxipos, "4-taxi")

        filename = os.path.join(basename + "-move.kml")
        with open(filename, "w") as fp:
            fp.write(toKML(cleanFeatures(self.moves_st)))
            logger.debug(":save: saved kml %s (%d)" % (filename, len(self.moves_st)))

        logger.debug(":save: saved %s" % self.flight_id)
        return (True, "Movement::save saved")


    def load(self):
        """
        Load flight paths from 3 files for flight plan, detailed movement, and taxi path.
        File must be saved by above save() function.
        """
        basename = os.path.join(AODB_DIR, FLIGHT_DATABASE, self.flight_id)

        filename = os.path.join(basename, "-plan.json")
        with open(filename, "r") as fp:
            self.moves = json.load(fp)

        filename = os.path.join(basename, "-move.json")
        with open(filename, "r") as fp:
            self.moves_st = json.load(fp)

        filename = os.path.join(basename, "-taxi.json")
        with open(filename, "r") as fp:
            self.taxipos = json.load(fp)

        logger.debug(":loadAll: loaded %d " % self.flight_id)
        return (True, "Movement::load loaded")


    def vnav(self):
        """
        Perform vertical navigation for route
        @todo: Add optional hold
        """

        def moveOnCP(fc, fcidx, currpos, dist):
            # move on dist (meters) on linestring from currpos (which is between fcidx and fcidx+1)
            # returns position after dist and new index, new position p is between i and i+1
            p, i = moveOn(fc, fcidx, currpos, dist)
            return (MovePoint(geometry=p["geometry"], properties=p["properties"]), i)

        def addCurrentPoint(coll, pos, oi, ni, color, mark, reverse: bool = False):
            # catch up adding all points in flight plan between oi, ni
            # then add pos (which is between ni and ni+1)
            # logger.debug(":addCurrentPoint: %d %d %s" % (oi, ni, reverse))
            if oi != ni:
                for idx in range(oi+1, ni+1):
                    i = idx if not reverse else len(self.flight.flightplan_cp) - idx - 1
                    wpt = self.flight.flightplan_cp[i]
                    p = MovePoint(geometry=wpt["geometry"], properties=wpt["properties"])
                    p.setColor(color)
                    p.setProp(FEATPROP.MARK.value, mark)
                    p.setProp(FEATPROP.FLIGHT_PLAN_INDEX.value, i)
                    p.setColor(POSITION_COLOR.FLIGHT_PLAN.value)  # remarkable point in GREEN
                    coll.append(p)
            coll.append(pos)
            # logger.debug(":addCurrentPoint: adding remarkable point: %s (%d)" % (pos.getProp(FEATPROP.MARK), len(coll)))
            # logger.debug(":addCurrentPoint: return index: %d" % (ni))
            # we now are at pos which is on LineString after index ni
            return ni

        def moveOnLS(coll, reverse, fc, fcidx, currpos, dist, alt, speed, vspeed, color, mark, mark_tr):
            # move on dist (meters) on linestring from currpos (which is between fcidx and fcidx+1)
            # returns position after dist and new index, new position p is between newidx and newidx+1
            p, newidx = moveOn(fc, fcidx, currpos, dist)
            logger.debug(":moveOnLS: from %d to %d (%s)" % (fcidx, newidx, mark))
            # from currpos after dist we will be at newpos
            newpos = MovePoint(geometry=p["geometry"], properties=p["properties"])
            newpos.setAltitude(alt)
            newpos.setSpeed(speed)
            newpos.setVSpeed(vspeed)
            newpos.setColor(color)
            newpos.setProp(FEATPROP.MARK.value, mark)
            return (newpos, addCurrentPoint(coll, newpos, fcidx, newidx, color, mark_tr, reverse))

        def addMovepoint(arr, src, alt, speed, vspeed, color, mark, ix):
            # create a copy of src, add properties on copy, and add copy to arr.
            logger.debug(":addMovepoint: %s %d" % (mark, ix))
            mvpt = MovePoint(geometry=src["geometry"], properties={})
            mvpt.setAltitude(alt)
            mvpt.setSpeed(speed)
            mvpt.setVSpeed(vspeed)
            mvpt.setColor(color)
            mvpt.setProp(FEATPROP.MARK.value, mark)
            mvpt.setProp(FEATPROP.FLIGHT_PLAN_INDEX.value, ix)
            arr.append(mvpt)
            return mvpt


        fc = self.flight.flightplan_cp
        ac = self.flight.aircraft
        actype = ac.actype
        # actype.perfs()
        logger.debug(":vnav: %s: %d points in flight plan" % (type(self).__name__, len(fc)))

        # for f in self.flight.flightplan_cp:
        #     logger.debug(":vnav: flight plan: %s" % (f.getProp("_plan_segment_type")))

        # PART 1: FORWARD: From takeoff to top of ascent
        #
        #
        logger.debug(":vnav: departure")
        groundmv = 0
        fcidx = 0

        if type(self).__name__ == "DepartureMove": # take off self.flight.is_departure()
            TOH_BLASTOFF = 0.2  # km
            rwy = self.flight.runway
            rwy_threshold = rwy.getPoint()
            alt = rwy_threshold.altitude()
            if alt is None:
                logger.warning(":vnav: departure airport has no altitude: %s" % rwy_threshold)
                alt = 0

            brg = bearing(rwy_threshold, rwy.end.getPoint())
            takeoff_hold = destination(rwy_threshold, TOH_BLASTOFF, brg, {"units": "km"})
            logger.debug(":vnav: departure from %s, %f" % (rwy.name, brg))

            p = addMovepoint(arr=self.moves,
                             src=takeoff_hold,
                             alt=alt,
                             speed=0,
                             vspeed=0,
                             color=POSITION_COLOR.TAKEOFF_HOLD.value,
                             mark=FLIGHT_PHASE.TAKEOFF_HOLD.value,
                             ix=0)
            self.takeoff_hold = copy.deepcopy(p)  # we keep this special position for taxiing (end_of_taxi)
            logger.debug(":vnav: takeoff hold at %s, %f" % (rwy.name, TOH_BLASTOFF))

            takeoff_distance = actype.getSI(ACPERF.takeoff_distance) * self.airport.runwayIsWet() / 1000  # must be km for destination()
            takeoff = destination(takeoff_hold, takeoff_distance, brg, {"units": "km"})

            p = addMovepoint(arr=self.moves,
                             src=takeoff,
                             alt=alt,
                             speed=actype.getSI(ACPERF.takeoff_speed),
                             vspeed=actype.getSI(ACPERF.initial_climb_speed),
                             color=POSITION_COLOR.TAKE_OFF.value,
                             mark=FLIGHT_PHASE.TAKE_OFF.value,
                             ix=0)
            groundmv = takeoff_distance
            logger.debug(":vnav: takeoff at %s, %f" % (rwy.name, takeoff_distance))

            # initial climb, commonly accepted to above 1500ft AGL
            logger.debug(":vnav: initialClimb")
            step = actype.initialClimb(alt)  # (t, d, altend)
            initial_climb_distance = step[1] / 1000  # km
            # find initial climb point

            # we climb on path to see if we reach indices...
            currpos, newidx = moveOn(fc, fcidx, p, initial_climb_distance)
            # we ignore currpos for now, we will climb straight, we ignore points
            # between fcidx and newidx during initial climb...
            initial_climb = destination(takeoff, initial_climb_distance, brg, {"units": "km"})
            currpos = addMovepoint(arr=self.moves,
                                   src=initial_climb,
                                   alt=alt,
                                   speed=actype.getSI(ACPERF.initial_climb_speed),
                                   vspeed=actype.getSI(ACPERF.initial_climb_vspeed),
                                   color=POSITION_COLOR.INITIAL_CLIMB.value,
                                   mark="end_initial_climb",
                                   ix=newidx)
            logger.debug(":vnav: initial climb end at %d, %f" % (newidx, initial_climb_distance))
            groundmv = groundmv + initial_climb_distance
            # we ignore vertices between takeoff and initial_climb
            # we go in straight line and ignore self.moves, skipping eventual points
            fcidx = newidx

        else:  # ArrivalMove, simpler departure
            deptapt = fc[0]
            alt = deptapt.altitude()
            if alt is None:
                logger.warning(":vnav: departure airport has no altitude: %s" % deptapt)
                alt = 0
            currpos = addMovepoint(arr=self.moves,
                                   src=deptapt,
                                   alt=alt,
                                   speed=actype.getSI(ACPERF.takeoff_speed),
                                   vspeed=actype.getSI(ACPERF.initial_climb_vspeed),
                                   color=POSITION_COLOR.TAKE_OFF.value,
                                   mark=FLIGHT_PHASE.TAKE_OFF.value,
                                   ix=fcidx)
            logger.debug(":vnav: origin added first point")

            # initial climb, commonly accepted to above 1500ft AGL
            logger.debug(":vnav: initialClimb")
            step = actype.initialClimb(alt)  # (t, d, altend)
            # find initial climb point
            groundmv = step[1]

            currpos, fcidx = moveOnLS(coll=self.moves, reverse=False,
                                      fc=fc,
                                      fcidx=fcidx,
                                      currpos=currpos,
                                      dist=step[1],
                                      alt=step[2],
                                      speed=actype.getSI(ACPERF.initial_climb_speed),
                                      vspeed=actype.getSI(ACPERF.initial_climb_vspeed),
                                      color=POSITION_COLOR.INITIAL_CLIMB.value,
                                      mark=FLIGHT_PHASE.INITIAL_CLIMB.value,
                                      mark_tr=FLIGHT_PHASE.INITIAL_CLIMB.value)

        logger.debug(":vnav: climbToFL100")
        step = actype.climbToFL100(currpos.altitude())  # (t, d, altend)
        groundmv = groundmv + step[1]
        currpos, fcidx = moveOnLS(coll=self.moves, reverse=False,
                                  fc=fc,
                                  fcidx=fcidx,
                                  currpos=currpos,
                                  dist=step[1],
                                  alt=step[2],
                                  speed=actype.fl100Speed(),
                                  vspeed=actype.getSI(ACPERF.climbFL150_vspeed),
                                  color=POSITION_COLOR.CLIMB.value,
                                  mark="end_fl100_climb",
                                  mark_tr=FLIGHT_PHASE.CLIMB.value)

        # climb to cruise altitude
        cruise_speed = actype.getSI(ACPERF.cruise_mach)

        if self.flight.flight_level >= 150:
            logger.debug(":vnav: climbToFL150")
            step = actype.climbToFL240(currpos.altitude())  # (t, d, altend)
            groundmv = groundmv + step[1]
            currpos, fcidx = moveOnLS(coll=self.moves, reverse=False,
                                      fc=fc,
                                      fcidx=fcidx,
                                      currpos=currpos,
                                      dist=step[1],
                                      alt=step[2],
                                      speed=actype.getSI(ACPERF.climbFL150_speed),
                                      vspeed=actype.getSI(ACPERF.climbFL150_vspeed),
                                      color=POSITION_COLOR.CLIMB.value,
                                      mark="end_fl150_climb",
                                      mark_tr=FLIGHT_PHASE.CLIMB.value)

            if self.flight.flight_level >= 240:
                logger.debug(":vnav: climbToFL240")
                step = actype.climbToFL240(currpos.altitude())  # (t, d, altend)
                groundmv = groundmv + step[1]
                currpos, fcidx = moveOnLS(coll=self.moves, reverse=False,
                                          fc=fc,
                                          fcidx=fcidx,
                                          currpos=currpos,
                                          dist=step[1],
                                          alt=step[2],
                                          speed=actype.getSI(ACPERF.climbFL240_speed),
                                          vspeed=actype.getSI(ACPERF.climbFL240_vspeed),
                                          color=POSITION_COLOR.CLIMB.value,
                                          mark="end_fl240_climb",
                                          mark_tr=FLIGHT_PHASE.CLIMB.value)

                if self.flight.flight_level > 240:
                    logger.debug(":vnav: climbToCruise")
                    step = actype.climbToCruise(currpos.altitude(), self.flight.getCruiseAltitude())  # (t, d, altend)
                    groundmv = groundmv + step[1]
                    currpos, fcidx = moveOnLS(coll=self.moves, reverse=False,
                                              fc=fc,
                                              fcidx=fcidx,
                                              currpos=currpos,
                                              dist=step[1],
                                              alt=step[2],
                                              speed=actype.getSI(ACPERF.climbmach_mach),
                                              vspeed=actype.getSI(ACPERF.climbmach_vspeed),
                                              color=POSITION_COLOR.TOP_OF_ASCENT.value,
                                              mark=FLIGHT_PHASE.TOP_OF_ASCENT.value,
                                              mark_tr=FLIGHT_PHASE.CLIMB.value)
                    # cruise speed defaults to ACPERF.cruise_mach, we don't need to specify it
            else:
                logger.debug(":vnav: climbToCruise below FL240")
                step = actype.climbToCruise(currpos.altitude(), self.flight.getCruiseAltitude())  # (t, d, altend)
                groundmv = groundmv + step[1]
                currpos, fcidx = moveOnLS(coll=self.moves, reverse=False,
                                          fc=fc,
                                          fcidx=fcidx,
                                          currpos=currpos,
                                          dist=step[1],
                                          alt=step[2],
                                          speed=actype.getSI(ACPERF.climbFL240_speed),
                                          vspeed=actype.getSI(ACPERF.climbFL240_vspeed),
                                          color=POSITION_COLOR.TOP_OF_ASCENT.value,
                                          mark=FLIGHT_PHASE.TOP_OF_ASCENT.value,
                                          mark_tr=FLIGHT_PHASE.CLIMB.value)
                cruise_speed = (actype.getSI(ACPERF.climbFL240_speed) + actype.getSI(ACPERF.cruise_mach))/ 2
                logger.warning(":vnav: cruise speed below FL240: %f m/s" % (cruise_speed))
        else:
            logger.debug(":vnav: climbToCruise below FL150")
            step = actype.climbToCruise(currpos.altitude(), self.flight.getCruiseAltitude())  # (t, d, altend)
            groundmv = groundmv + step[1]
            currpos, fcidx = moveOnLS(coll=self.moves, reverse=False,
                                      fc=fc,
                                      fcidx=fcidx,
                                      currpos=currpos,
                                      dist=step[1],
                                      alt=step[2],
                                      speed=actype.getSI(ACPERF.climbFL240_speed),
                                      vspeed=actype.getSI(ACPERF.climbFL240_vspeed),
                                      color=POSITION_COLOR.TOP_OF_ASCENT.value,
                                      mark=FLIGHT_PHASE.TOP_OF_ASCENT.value,
                                      mark_tr=FLIGHT_PHASE.CLIMB.value)
            logger.warning(":vnav: cruise speed below FL150: %f m/s" % (cruise_speed))
            cruise_speed = (actype.getSI(ACPERF.climbFL150_speed) + actype.getSI(ACPERF.cruise_mach))/ 2

        # accelerate to cruise speed smoothly
        ACCELERATION_DISTANCE = 5000  # we reach cruise speed after 5km horizontal flight
        logger.debug(":vnav: accelerate to cruise speed")
        currpos, fcidx = moveOnLS(coll=self.moves, reverse=False,
                                  fc=fc,
                                  fcidx=fcidx,
                                  currpos=currpos,
                                  dist=ACCELERATION_DISTANCE,
                                  alt=step[2],
                                  speed=cruise_speed,
                                  vspeed=0,
                                  color=POSITION_COLOR.CRUISE.value,
                                  mark="reached_cruise_speed",
                                  mark_tr=FLIGHT_PHASE.CRUISE.value)

        top_of_ascent_idx = fcidx + 1 # we reach top of ascent between idx and idx+1, so we cruise from idx+1 on.
        logger.debug(":vnav: cruise at %d after %f" % (top_of_ascent_idx, groundmv))
        logger.debug(":vnav: ascent added (+%d %d)" % (len(self.moves), len(self.moves)))
        # cruise until top of descent

        # PART 2: REVERSE: From brake on runway to top of descent
        #
        #
        logger.debug(":vnav: arrival")
        APPROACH_ALT = 3000*FT  # Altitude ABG at which we perform approach path before final
        STAR_ALT = 6000*FT      # Altitude ABG at which we perform STAR path before approach
        LAND_TOUCH_DOWN = 0.4   # km, distance of touch down from the runway threshold (given in CIFP)

        revmoves = []
        groundmv = 0
        fc = self.flight.flightplan_cp.copy()
        fc.reverse()
        fcidx = 0

        if type(self).__name__ == "ArrivalMove": # the path starts at the of roll out
            rwy = self.flight.runway
            rwy_threshold = rwy.getPoint()
            alt = rwy_threshold.altitude()
            if alt is None:
                logger.warning(":vnav:(rev) departure airport has no altitude: %s" % rwy_threshold)
                alt = 0

            brg = bearing(rwy_threshold, rwy.end.getPoint())
            touch_down = destination(rwy_threshold, LAND_TOUCH_DOWN, brg, {"units": "km"})
            logger.debug(":vnav:(rev) arrival runway %s, %f" % (rwy.name, brg))

            # First point is end off roll out, read to exit the runway and taxi
            rollout_distance = actype.getSI(ACPERF.landing_distance) * self.airport.runwayIsWet() / 1000 # must be km for destination()
            end_rollout = destination(touch_down, rollout_distance, brg, {"units": "km"})

            currpos = addMovepoint(arr=revmoves,
                                   src=end_rollout,
                                   alt=alt,
                                   speed=TAXI_SPEED,
                                   vspeed=0,
                                   color=POSITION_COLOR.ROLL_OUT.value,
                                   mark=FLIGHT_PHASE.END_ROLLOUT.value,
                                   ix=len(fc)-fcidx)
            logger.debug(":vnav:(rev) end roll out at %s, %f, %f" % (rwy.name, rollout_distance, alt))
            self.end_rollout = copy.deepcopy(currpos)  # we keep this special position for taxiing (start_of_taxi)

            # Point just before before is touch down
            currpos = addMovepoint(arr=revmoves,
                                   src=touch_down,
                                   alt=alt,
                                   speed=actype.getSI(ACPERF.landing_speed),
                                   vspeed=0,
                                   color=POSITION_COLOR.TOUCH_DOWN.value,
                                   mark=FLIGHT_PHASE.TOUCH_DOWN.value,
                                   ix=len(fc)-fcidx)
            logger.debug(":vnav:(rev) touch down at %s, %f, %f" % (rwy.name, LAND_TOUCH_DOWN, alt))

        else:
            arrvapt = fc[fcidx]
            alt = arrvapt.altitude()
            if alt is None:
                logger.warning(":vnav:(rev) arrival airport has no altitude: %s" % arrvapt)
                alt = 0

            currpos = addMovepoint(arr=revmoves,
                                   src=arrvapt,
                                   alt=alt,
                                   speed=actype.getSI(ACPERF.landing_speed),
                                   vspeed=actype.getSI(ACPERF.approach_vspeed),
                                   color=POSITION_COLOR.DESTINATION.value,
                                   mark="destination",
                                   ix=len(fc)-fcidx)
            logger.debug(":vnav:(rev) destination added last point")

        # we move to the final fix at max 3000ft, approach speed
        logger.debug(":vnav:(rev) final")
        step = actype.descentFinal(alt+APPROACH_ALT, alt)  # (t, d, altend)
        groundmv = groundmv + step[1]
        # find initial climb point
        currpos, fcidx = moveOnLS(coll=revmoves, reverse=True,
                                  fc=fc,
                                  fcidx=fcidx,
                                  currpos=currpos,
                                  dist=step[1],
                                  alt=alt+APPROACH_ALT,
                                  speed=actype.getSI(ACPERF.landing_speed),
                                  vspeed=actype.getSI(ACPERF.approach_vspeed),
                                  color=POSITION_COLOR.FINAL.value,
                                  mark="start_of_final",
                                  mark_tr=FLIGHT_PHASE.FINAL.value)

        if type(self).__name__ == "ArrivalMove":
            # find first point of approach:
            k = len(fc) - 1
            while fc[k].getProp("_plan_segment_type") != "appch" and k > 0:
                k = k - 1
            if k == 0:
                logger.warning(":vnav: no approach found")
            else:
                logger.debug(":vnav:(rev) start of approach at index %d, %s" % (k, fc[k].getProp("_plan_segment_type")))
                if k <= fcidx:
                    logger.debug(":vnav:(rev) final fix seems further away than start of apprach")
                else:
                    logger.debug(":vnav:(rev) flight level to final fix")
                    # add all approach points between start to approach to final fix
                    for i in range(fcidx+1, k):
                        wpt = fc[i]
                        # logger.debug(":vnav: APPCH: flight level: %d %s" % (i, wpt.getProp("_plan_segment_type")))
                        p = addMovepoint(arr=revmoves,
                                         src=wpt,
                                         alt=alt+APPROACH_ALT,
                                         speed=actype.getSI(ACPERF.approach_speed),
                                         vspeed=0,
                                         color=POSITION_COLOR.APPROACH.value,
                                         mark=FLIGHT_PHASE.APPROACH.value,
                                         ix=len(fc)-i)
                        # logger.debug(":vnav: adding remarkable point: %d %s (%d)" % (i, p.getProp(FEATPROP.MARK), len(revmoves)))

                    # add start of approach
                    currpos = addMovepoint(arr=revmoves,
                                           src=fc[k],
                                           alt=alt+APPROACH_ALT,
                                           speed=actype.getSI(ACPERF.approach_speed),
                                           vspeed=0,
                                           color=POSITION_COLOR.APPROACH.value,
                                           mark="start_of_approach",
                                           ix=len(fc)-k)
                    # logger.debug(":vnav: adding remarkable point: %d %s (%d)" % (k, currpos.getProp(FEATPROP.MARK), len(revmoves)))

                    fcidx = k

            # find first point of star:
            k = len(fc) - 1
            while fc[k].getProp("_plan_segment_type") != "star" and k > 0:
                k = k - 1
            if k == 0:
                logger.warning(":vnav:(rev) no star found")
            else:
                logger.debug(":vnav:(rev) start of star at index %d, %s" % (k, fc[k].getProp("_plan_segment_type")))
                if k <= fcidx:
                    logger.debug(":vnav:(rev) final fix seems further away than start of star")
                else:
                    logger.debug(":vnav:(rev) flight level to start of approach")
                    # add all approach points between start to approach to final fix
                    for i in range(fcidx+1, k):
                        wpt = fc[i]
                        # logger.debug(":vnav: STAR: flight level: %d %s" % (i, wpt.getProp("_plan_segment_type")))
                        p = addMovepoint(arr=revmoves,
                                         src=wpt,
                                         alt=alt+STAR_ALT,
                                         speed=actype.getSI(ACPERF.approach_speed),
                                         vspeed=0,
                                         color=POSITION_COLOR.APPROACH.value,
                                         mark="star",
                                         ix=len(fc)-i)

                        # logger.debug(":vnav: adding remarkable point: %d %s (%d)" % (i, p.getProp(FEATPROP.MARK), len(revmoves)))
                    # add start of approach
                    currpos = addMovepoint(arr=revmoves,
                                           src=fc[k],
                                           alt=alt+STAR_ALT,
                                           speed=actype.getSI(ACPERF.approach_speed),
                                           vspeed=0,
                                           color=POSITION_COLOR.APPROACH.value,
                                           mark="start_of_star",
                                           ix=len(fc)-k)
                    # logger.debug(":vnav: adding remarkable point: %d %s (%d)" % (k, currpos.getProp(FEATPROP.MARK), len(revmoves)))
                    #
                    # @todo: We assume start of star is where holding occurs
                    self.holdingpoint = fc[k].id
                    # logger.debug(":vnav: searching for holding fix at %s" % (self.holdingpoint))
                    # holds = self.airport.airspace.findHolds(self.holdingpoint)
                    # if len(holds) > 0:
                    #     holding = holds[0]  # keep fist one
                    #     logger.debug(":vnav: found holding fix at %s (%d found), adding pattern.." % (holding.fix.id, len(holds)))
                    #     hold_pts = holding.getRoute(actype.getSI(ACPERF.approach_speed))
                    #     # !!! since the pattern is added to revmoves (which is reversed!)
                    #     # we need to reverse the pattern before adding it.
                    #     # it will be inversed again (back to its original sequence)
                    #     # at revmoves.reverse().
                    #     hold_pts.reverse()
                    #     holdidx = len(hold_pts)
                    #     for hp in hold_pts:
                    #         p = MovePoint(geometry=hp["geometry"], properties=hp["properties"])
                    #         p.setAltitude(alt+STAR_ALT)
                    #         p.setSpeed(actype.getSI(ACPERF.approach_speed))
                    #         p.setVSpeed(0)
                    #         p.setColor(POSITION_COLOR.HOLDING.value)
                    #         p.setProp(FEATPROP.MARK.value, FLIGHT_PHASE.HOLDING.value)
                    #         p.setProp(FEATPROP.FLIGHT_PLAN_INDEX.value, i)
                    #         p.setProp("holding-pattern-idx", holdidx)
                    #         holdidx = holdidx - 1
                    #         revmoves.append(p)
                    #     logger.debug(":vnav: .. done (%d points added)" % (len(hold_pts)))
                    # else:
                    #     logger.debug(":vnav: holding fix %s not found" % (self.holdingpoint))

                    fcidx = k

        if self.flight.flight_level > 100:
            # descent from FL100 to first approach point
            logger.debug(":vnav:(rev) descent to star alt")
            step = actype.descentApproach(10000*FT, alt+STAR_ALT)  # (t, d, altend)
            groundmv = groundmv + step[1]
            currpos, fcidx = moveOnLS(coll=revmoves, reverse=True,
                                      fc=fc,
                                      fcidx=fcidx,
                                      currpos=currpos,
                                      dist=step[1],
                                      alt=10000*FT,
                                      speed=actype.getSI(ACPERF.approach_speed),
                                      vspeed=actype.getSI(ACPERF.approach_vspeed),
                                      color=POSITION_COLOR.DESCEND.value,
                                      mark="descent_fl100_reached",
                                      mark_tr=FLIGHT_PHASE.DESCEND.value)

            if self.flight.flight_level > 240:
                # descent from FL240 to FL100
                logger.debug(":vnav:(rev) descent to FL100")
                step = actype.descentToFL100(24000*FT)  # (t, d, altend)
                groundmv = groundmv + step[1]
                currpos, fcidx = moveOnLS(coll=revmoves, reverse=True,
                                          fc=fc,
                                          fcidx=fcidx,
                                          currpos=currpos,
                                          dist=step[1],
                                          alt=24000*FT,
                                          speed=actype.getSI(ACPERF.descentFL100_speed),
                                          vspeed=actype.getSI(ACPERF.descentFL100_vspeed),
                                          color=POSITION_COLOR.DESCEND.value,
                                          mark="descent_fl240_reached",
                                          mark_tr=FLIGHT_PHASE.DESCEND.value)

                if self.flight.flight_level > 240:
                    # descent from cruise above FL240 to FL240
                    logger.debug(":vnav:(rev) descent from cruise alt to FL240")
                    step = actype.descentToFL240(self.flight.getCruiseAltitude())  # (t, d, altend)
                    groundmv = groundmv + step[1]
                    currpos, fcidx = moveOnLS(coll=revmoves, reverse=True,
                                              fc=fc,
                                              fcidx=fcidx,
                                              currpos=currpos,
                                              dist=step[1],
                                              alt=self.flight.getCruiseAltitude(),
                                              speed=actype.getSI(ACPERF.descentFL240_mach),
                                              vspeed=actype.getSI(ACPERF.descentFL240_vspeed),
                                              color=POSITION_COLOR.TOP_OF_DESCENT.value,
                                              mark=FLIGHT_PHASE.TOP_OF_DESCENT.value,
                                              mark_tr=FLIGHT_PHASE.DESCEND.value)

            else:
                # descent from cruise below FL240 to FL100
                logger.debug(":vnav:(rev) descent from cruise alt under FL240 to FL100")
                step = actype.descentToFL100(self.flight.getCruiseAltitude())  # (t, d, altend)
                groundmv = groundmv + step[1]
                currpos, fcidx = moveOnLS(coll=revmoves, reverse=True,
                                          fc=fc,
                                          fcidx=fcidx,
                                          currpos=currpos,
                                          dist=step[1],
                                          alt=self.flight.getCruiseAltitude(),
                                          speed=actype.getSI(ACPERF.descentFL100_speed),
                                          vspeed=actype.getSI(ACPERF.descentFL100_vspeed),
                                          color=POSITION_COLOR.DESCEND.value,
                                          mark=FLIGHT_PHASE.TOP_OF_DESCENT.value,
                                          mark_tr=FLIGHT_PHASE.DESCEND.value)
        else:
            # descent from cruise below FL100 to approach alt
            logger.debug(":vnav:(rev) descent from cruise alt under FL100 to approach alt")
            step = actype.descentApproach(self.flight.getCruiseAltitude(), alt+APPROACH_ALT)  # (t, d, altend)
            groundmv = groundmv + step[1]
            currpos, fcidx = moveOnLS(coll=revmoves, reverse=True,
                                      fc=fc,
                                      fcidx=fcidx,
                                      currpos=currpos,
                                      dist=step[1],
                                      alt=self.flight.getCruiseAltitude(),
                                      speed=actype.getSI(ACPERF.approach_speed),
                                      vspeed=actype.getSI(ACPERF.approach_vspeed),
                                      color=POSITION_COLOR.DESCEND.value,
                                      mark=FLIGHT_PHASE.TOP_OF_DESCENT.value,
                                      mark_tr=FLIGHT_PHASE.DESCEND.value)

        # decelerate to descent speed smoothly
        DECELERATION_DISTANCE = 5000  # we reach cruise speed after 5km horizontal flight
        logger.debug(":vnav:(rev) decelerate from cruise speed to first descent speed (which depends on alt...)")
        currpos, newidx = moveOnCP(fc, fcidx, currpos, DECELERATION_DISTANCE)
        groundmv = groundmv + DECELERATION_DISTANCE
        currpos, fcidx = moveOnLS(coll=revmoves, reverse=True,
                                  fc=fc,
                                  fcidx=fcidx,
                                  currpos=currpos,
                                  dist=step[1],
                                  alt=self.flight.getCruiseAltitude(),
                                  speed=cruise_speed,
                                  vspeed=0,
                                  color=POSITION_COLOR.CRUISE.value,
                                  mark="end_of_cruise_speed",
                                  mark_tr=FLIGHT_PHASE.CRUISE.value)

        top_of_decent_idx = fcidx + 1 # we reach top of descent between idx and idx+1, so we cruise until idx+1
        logger.debug(":vnav:(rev) reverse descent at %d after %f" % (top_of_decent_idx, groundmv))
        # we .reverse() array:
        top_of_decent_idx = len(self.flight.flightplan_cp) - top_of_decent_idx  - 1
        logger.debug(":vnav:(rev) cruise until %d, descent after %d, remains %f to destination" % (top_of_decent_idx, top_of_decent_idx, groundmv))

        # PART 3: Join top of ascent to top of descent at cruise speed
        #
        # We copy waypoints from start of cruise to end of cruise
        logger.debug(":vnav: cruise")
        if top_of_decent_idx > top_of_ascent_idx:
            # logger.debug(":vnav: adding cruise: %d -> %d" % (top_of_ascent_idx, top_of_decent_idx))
            for i in range(top_of_ascent_idx, top_of_decent_idx):
                wpt = self.flight.flightplan_cp[i]
                # logger.debug(":vnav: adding cruise: %d %s" % (i, wpt.getProp("_plan_segment_type")))

                p = addMovepoint(arr=self.moves,
                                 src=wpt,
                                 alt=self.flight.getCruiseAltitude(),
                                 speed=cruise_speed,
                                 vspeed=0,
                                 color=POSITION_COLOR.CRUISE.value,
                                 mark=FLIGHT_PHASE.CRUISE.value,
                                 ix=i)
            logger.debug(":vnav: cruise added (+%d %d)" % (top_of_decent_idx - top_of_ascent_idx, len(self.moves)))
        else:
            logger.warning(":vnav: cruise too short (%d -> %d)" % (top_of_ascent_idx, top_of_decent_idx))

        # PART 4: Add descent and final
        #
        #
        revmoves.reverse()
        self.moves = self.moves + revmoves
        logger.debug(":vnav: descent added (+%d %d)" % (len(revmoves), len(self.moves)))
        # printFeatures(self.moves, "holding")
        return (True, "Movement::vnav completed without restriction")


    def standard_turns(self):
        # @todo: Should supress ST when turn is too small (< 10°) (done in st_flyby())
        #        Should supress ST when points too close (leg < 10 second move at constant speed)
        def turnRadius(speed):  # speed in m/s, returns radius in m
            return 120 * speed / (2 * pi)

        def should_do_st(path, idx):
            mark = path[idx].getProp(FEATPROP.MARK.value)
            return mark not in [FLIGHT_PHASE.TAKE_OFF.value,
                                "end_initial_climb",
                                FLIGHT_PHASE.TOUCH_DOWN.value,
                                FLIGHT_PHASE.END_ROLLOUT.value]

        self.moves_st = []
        last_speed = 100  # @todo: should fetch another reasonable value from aircraft performance.
        # Add first point
        self.moves_st.append(self.moves[0])

        for i in range(1, len(self.moves) - 1):
            if not should_do_st(self.moves, i):
                logger.debug(":standard_turns: skipping %d (special mark)" % (i))
                self.moves_st.append(self.moves[i])
            else:
                li = LineString([self.moves[i-1]["geometry"]["coordinates"], self.moves[i]["geometry"]["coordinates"]])
                lo = LineString([self.moves[i]["geometry"]["coordinates"], self.moves[i+1]["geometry"]["coordinates"]])
                s = last_speed  # arrin[i].speed()
                if s is None:
                    s = last_speed
                arc = standard_turn_flyby(li, lo, turnRadius(s))
                last_speed = s

                if arc is not None:
                    mid = arc[int(len(arc) / 2)]
                    mid["properties"] = self.moves[i]["properties"]
                    for p in arc:
                        self.moves_st.append(MovePoint(geometry=p["geometry"], properties=mid["properties"]))
                else:
                    self.moves_st.append(self.moves[i])

        # Add last point too
        self.moves_st.append(self.moves[-1])
        logger.debug(":standard_turns: completed %d, %d" % (len(self.moves), len(self.moves_st)))
        return (True, "Movement::standard_turns added")


    def interpolate(self):
        """
        Compute interpolated values for altitude and speed based on distance.
        This is a simple linear interpolation based on distance between points.
        Runs for flight portion of flight.
        """
        to_interp = self.moves_st
        # before = []

        logger.debug(":interpolate: interpolating ..")
        for name in ["speed", "vspeed", "altitude"]:
            logger.debug(":interpolate: .. %s .." % (name))
            # before = list(map(lambda x: x.getProp(name), to_interp))
            status = doInterpolation(to_interp, name)
            if not status[0]:
                logger.warning(status[1])
        logger.debug(":interpolate: .. done.")

        logger.debug(":interpolate: checking and transposing altitudes to geojson coordinates..")
        for f in to_interp:
            if len(f["geometry"]["coordinates"]) == 2:
                a = f.altitude()
                if a is not None:
                    f["geometry"]["coordinates"].append(float(a))
                else:
                    logger.warning(":interpolate: not altitude?%s" % (f["geometry"]["name"]if name in f["geometry"] else "?"))
        logger.debug(":interpolate: .. done.")
        # for i in range(len(to_interp)):
        #     v = to_interp[i].getProp(name) if to_interp[i].getProp(name) is not None and to_interp[i].getProp(name) != "None" else -1
        #     logger.debug(":interpolate: %d: %s -> %s." % (i, before[i] if before[i] is not None else -1, v))


        # logger.debug(":interpolate: last point %d: %f, %f" % (len(self.moves_st), self.moves_st[-1].speed(), self.moves_st[-1].altitude()))
        # i = 0
        # for f in self.moves:
        #     s = f.speed()
        #     a = f.altitude()
        #     logger.debug(":vnav: alter: %d: %f %f" % (i, s if s is not None else -1, a if a is not None else -1))
        #     i = i + 1

        return (True, "Movement::interpolated speed and altitude")


    def time(self):
        """
        Time 0 is start of roll for takeoff (Departure) or takeoff from origin airport (Arrival).
        Last time is touch down at destination (Departure) or end of roll out (Arrival).
        """
        if self.moves_st is None:
            return (False, "Movement::time no move")

        status = doTime(self.moves_st)
        if not status[0]:
            logger.warning(status[1])
            return status

        return (True, "Movement::time computed")


    def taxi(self):
        return (False, "Movement::taxi done")


    def taxiInterpolateAndTime(self):
        """
        Time 0 is start of pushback (Departure) or end of roll out (Arrival).
        Last time is take off hold (Departure) or parking (Arrival).
        """
        if self.taxipos is None:
            return (False, "Movement::taxiInterpolateAndTime no move")

        logger.debug(":taxiInterpolateAndTime: interpolate speed ..")
        status = doInterpolation(self.taxipos, "speed")
        if not status[0]:
            logger.warning(status[1])
            return status

        logger.debug(":taxiInterpolateAndTime: .. compute time ..")
        status = doTime(self.taxipos)
        if not status[0]:
            logger.warning(status[1])
            return status

        logger.debug(":taxiInterpolateAndTime: .. done.")

        return (True, "Movement::taxiInterpolateAndTime done")


    def add_tmo(self):
        # We add a TMO point (Ten (nautical) Miles Out). Should be set before we interpolate.
        TMO = 10 * NAUTICAL_MILE  # km
        idx = len(self.moves_st) - 1  # last is end of roll, before last is touch down.
        totald = 0
        prev = 0
        while totald < TMO and idx > 1:
            idx = idx - 1
            d = distance(self.moves_st[idx], self.moves_st[idx-1])
            prev = totald
            totald = totald + d
            # logger.debug("add_tmo: %d: d=%f, t=%f" % (idx, d, totald))
        # idx points at
        left = TMO - prev
        # logger.debug("add_tmo: %d: left=%f, TMO=%f" % (idx, left, TMO))
        brng = bearing(self.moves_st[idx], self.moves_st[idx - 1])
        tmopt = destination(self.moves_st[idx], left, brng, {"units": "km"})

        tmomp = MovePoint(geometry=tmopt["geometry"], properties={})
        tmomp.setProp(FEATPROP.MARK.value, "TMO")

        d = distance(tmomp, self.moves_st[-2])  # last is end of roll, before last is touch down.

        self.moves_st.insert(idx, tmomp)
        logger.debug(":add_tmo: added at ~%f km, ~%f nm from touch down" % (d, d / NAUTICAL_MILE))

        return (True, "Movement::add_tmo added")


    def addDelay(self, name: str, seconds: int):
        farr = findFeatures(self.moves_st, {FEATPROP.MARK.value: name})
        if len(farr) == 0:
            logger.warning(":addDelay: feature mark %s not found" % name)
            return
        ## assume at most one...
        f = farr[0]
        f.setProp(FEATPROP.DELAY.value, seconds)


class ArrivalMove(Movement):
    """
    Movement for an arrival flight
    """
    def __init__(self, flight: Flight, airport: AirportBase):
        Movement.__init__(self, flight=flight, airport=airport)


    def taxi(self):
        """
        Compute taxi path for arrival, from roll out position, to runway exit to parking.
        """
        show_pos = False
        fc = []

        endrolloutpos = MovePoint(geometry=self.end_rollout["geometry"], properties=self.end_rollout["properties"])
        endrolloutpos.setSpeed(TAXI_SPEED)
        endrolloutpos.setColor("#880088")  # parking
        endrolloutpos.setProp(FEATPROP.MARK.value, "end rollout")
        fc.append(endrolloutpos)

        rwy = self.flight.runway
        rwy_threshold = rwy.getPoint()
        landing_distance = distance(rwy_threshold, endrolloutpos)
        rwy_exit = self.airport.closest_runway_exit(rwy.name, landing_distance)

        taxi_start = self.airport.taxiways.nearest_point_on_edge(rwy_exit)
        if show_pos:
            logger.debug(":taxi:in: taxi start: %s" % taxi_start)
        else:
            logger.debug(":taxi:in: taxi start: exit runway %s" % rwy.name)
        if taxi_start[0] is None:
            logger.warning(":taxi:in: could not find taxi start")
        taxistartpos = MovePoint(geometry=taxi_start[0]["geometry"], properties=taxi_start[0]["properties"])
        taxistartpos.setSpeed(TAXI_SPEED)
        taxistartpos.setColor("#880088")  # parking
        taxistartpos.setProp(FEATPROP.MARK.value, "taxi start")
        fc.append(taxistartpos)

        taxistart_vtx = self.airport.taxiways.nearest_vertex(taxi_start[0])
        if show_pos:
            logger.debug(":taxi:in: taxi start vtx: %s" % taxistart_vtx)
        if taxistart_vtx[0] is None:
            logger.warning(":taxi:in: could not find taxi start vertex")
        taxistartpos = MovePoint(geometry=taxistart_vtx[0]["geometry"], properties=taxistart_vtx[0]["properties"])
        taxistartpos.setSpeed(TAXI_SPEED)
        taxistartpos.setColor("#880088")  # parking
        taxistartpos.setProp(FEATPROP.MARK.value, "taxi start vertex")
        fc.append(taxistartpos)

        parking = self.flight.ramp
        if show_pos:
            logger.debug(":taxi:in: parking: %s" % parking)
        # we call the move from packing position to taxiway network the "parking entry"
        parking_entry = self.airport.taxiways.nearest_point_on_edge(parking)
        if show_pos:
            logger.debug(":taxi:in: parking_entry: %s" % parking_entry[0])

        if parking_entry[0] is None:
            logger.warning(":taxi:in: could not find parking entry")

        parkingentry_vtx = self.airport.taxiways.nearest_vertex(parking_entry[0])
        if parkingentry_vtx[0] is None:
            logger.warning(":taxi:in: could not find parking entry vertex")
        if show_pos:
            logger.debug(":taxi:in: parkingentry_vtx: %s " % parkingentry_vtx[0])

        taxi_ride = Route(self.airport.taxiways, taxistart_vtx[0].id, parkingentry_vtx[0].id)
        if taxi_ride.found():
            for vtx in taxi_ride.get_vertices():
                # vtx = self.airport.taxiways.get_vertex(vid)
                taxipos = MovePoint(geometry=vtx["geometry"], properties=vtx["properties"])
                taxipos.setSpeed(TAXI_SPEED)
                taxipos.setColor("#880000")  # taxi
                taxipos.setProp(FEATPROP.MARK.value, "taxi")
                taxipos.setProp("_taxiways", vtx.id)
                fc.append(taxipos)
            fc[-1].setProp(FEATPROP.MARK.value, "taxi end vertex")
        else:
            logger.warning(":taxi:in: no taxi route found")

        parkingentrypos = MovePoint(geometry=parking_entry[0]["geometry"], properties=parking_entry[0]["properties"])
        parkingentrypos.setSpeed(SLOW_SPEED)
        parkingentrypos.setColor("#880088")  # parking entry, is on taxiway network
        parkingentrypos.setProp(FEATPROP.MARK.value, "taxi end")
        fc.append(parkingentrypos)

        parkingpos = MovePoint(geometry=parking["geometry"], properties=parking["properties"])
        parkingpos.setSpeed(0)
        parkingpos.setColor("#880088")  # parking
        parkingpos.setProp(FEATPROP.MARK.value, "parking")
        fc.append(parkingpos)

        if show_pos:
            logger.debug(":taxi:in: taxi end: %s" % parking)
        else:
            logger.debug(":taxi:in: taxi end: parking %s" % parking.getProp("name"))

        self.taxipos = fc
        logger.debug(":taxi:in: taxi %d moves" % (len(self.taxipos)))

        return (True, "ArrivalMove::taxi completed")


class DepartureMove(Movement):
    """
    Movement for an departure flight
    """
    def __init__(self, flight: Flight, airport: AirportBase):
        Movement.__init__(self, flight=flight, airport=airport)


    def taxi(self):
        """
        Compute taxi path for departure, from parking to take-off hold location.
        """
        show_pos = False
        fc = []

        parking = self.flight.ramp
        if show_pos:
            logger.debug(":taxi:out: parking: %s" % parking)
        else:
            logger.debug(":taxi:out: taxi start: parking %s" % parking.getProp("name"))
        parkingpos = MovePoint(geometry=parking["geometry"], properties=parking["properties"])
        parkingpos.setSpeed(0)
        parkingpos.setColor("#880088")  # parking
        parkingpos.setProp(FEATPROP.MARK.value, "parking")
        fc.append(parkingpos)
        if show_pos:
            logger.debug(":taxi:out: taxi start: %s" % parkingpos)

        # we call the move from packing position to taxiway network the "pushback"
        pushback_end = self.airport.taxiways.nearest_point_on_edge(parking)
        if show_pos:
            logger.debug(":taxi:out: pushback_end: %s" % pushback_end[0])
        if pushback_end[0] is None:
            logger.warning(":taxi:out: could not find pushback end")

        pushbackpos = MovePoint(geometry=pushback_end[0]["geometry"], properties=pushback_end[0]["properties"])
        pushbackpos.setSpeed(SLOW_SPEED)
        pushbackpos.setColor("#880088")  # parking
        pushbackpos.setProp(FEATPROP.MARK.value, "pushback")
        fc.append(pushbackpos)

        pushback_vtx = self.airport.taxiways.nearest_vertex(pushback_end[0])
        if show_pos:
            logger.debug(":taxi:out: pushback_vtx: %s" % pushback_vtx[0])
        if pushback_vtx[0] is None:
            logger.warning(":taxi:out: could not find pushback end vertex")

        last_vtx = pushback_vtx

        if TAKEOFF_QUEUE_SIZE > 0:
            # Taxi from pushback to start of queue
            #
            rwy = self.flight.runway

            queuepnt = self.airport.queue_point(rwy.name, 0)
            queuerwy = self.airport.taxiways.nearest_point_on_edge(queuepnt)
            if show_pos:
                logger.debug(":taxi:out: start of queue point: %s" % queuerwy[0])
            if queuerwy[0] is None:
                logger.warning(":taxi:out: could not find start of queue point")

            queuerwy_vtx = self.airport.taxiways.nearest_vertex(queuerwy[0])
            if show_pos:
                logger.debug(":taxi:out: queuerwy_vtx %s" % queuerwy_vtx[0])
            if queuerwy_vtx[0] is None:
                logger.warning(":taxi:out: could not find start of queue vertex")

            taxi_ride = Route(self.airport.taxiways, pushback_vtx[0].id, queuerwy_vtx[0].id)
            if taxi_ride.found():
                for vtx in taxi_ride.get_vertices():
                    taxipos = MovePoint(geometry=vtx["geometry"], properties=vtx["properties"])
                    taxipos.setSpeed(TAXI_SPEED)
                    taxipos.setColor("#880000")  # taxi
                    taxipos.setProp(FEATPROP.MARK.value, "taxi")
                    taxipos.setProp("_taxiways", vtx.id)
                    fc.append(taxipos)
                fc[-1].setProp(FEATPROP.MARK.value, "taxi start of queue")
            else:
                logger.warning(":taxi:out: no taxi route found to start of queue")

            # Taxi from queue point 1 to last, stay on to taxiway edges
            #
            last_queue_on = None
            cnt = 0
            for i in range(1, len(self.airport.takeoff_queues[rwy.name])):
                queuepnt = self.airport.queue_point(rwy.name, i)
                queuerwy = self.airport.taxiways.nearest_point_on_edge(queuepnt)
                # logger.debug(":taxi: queue_point: %s" % queuerwy[0])
                if queuerwy[0] is None:
                    logger.warning(":taxi:out: could not place queue on taxiway")
                else:
                    last_queue_on = queuerwy
                    qspos = MovePoint(geometry=queuerwy[0]["geometry"], properties=queuerwy[0]["properties"])
                    qspos.setSpeed(TAXI_SPEED)
                    qspos.setColor("#880000")
                    qspos.setProp(FEATPROP.MARK.value, "queue %s" % i)
                    fc.append(qspos)
                    cnt = cnt + 1
            logger.warning(":taxi:out: added %d queue points" % cnt)

            if last_queue_on[0] is None:
                logger.warning(":taxi:out: could not find last queue point")
            else:
                last_queue_vtx = self.airport.taxiways.nearest_vertex(last_queue_on[0])
                if last_queue_vtx[0] is None:
                    # BIG PROBLEM IF POINT last_queue_on WAS ADDED AND CANNOT FIND VERTEX
                    logger.warning(":taxi:out: could not find last queue vertex")
                else:
                    last_vtx = last_queue_vtx

        # Taxi from end of queue to takeoff-hold
        #
        taxi_end = self.airport.taxiways.nearest_point_on_edge(self.takeoff_hold)
        if show_pos:
            logger.debug(":taxi:out: taxi_end: %s" % taxi_end[0])
        if taxi_end[0] is None:
            logger.warning(":taxi:out: could not find taxi end")

        taxiend_vtx = self.airport.taxiways.nearest_vertex(taxi_end[0])
        if show_pos:
            logger.debug(":taxi: taxiend_vtx %s" % taxiend_vtx[0])
        if taxiend_vtx[0] is None:
            logger.warning(":taxi:out: could not find taxi end vertex")

        taxi_ride = self.airport.taxiways.AStar(last_vtx[0].id, taxiend_vtx[0].id)
        logger.debug(":taxi:out: taxi_ride: %s -> %s: %s" % (last_vtx[0].id, taxiend_vtx[0].id, taxi_ride))

        dummy = self.airport.taxiways.AStar(taxiend_vtx[0].id, last_vtx[0].id)
        logger.debug(":taxi:out: taxi_ride inverted: %s -> %s: %s" % (taxiend_vtx[0].id, last_vtx[0].id, dummy))

        if taxi_ride is None and dummy is not None:
            logger.debug(":taxi:out: using taxi_ride inverted")
            taxi_ride = dummy
            taxi_ride.reverse()

        if taxi_ride is not None:
            for vid in taxi_ride:
                vtx = self.airport.taxiways.get_vertex(vid)
                taxipos = MovePoint(geometry=vtx["geometry"], properties=vtx["properties"])
                taxipos.setSpeed(TAXI_SPEED)
                taxipos.setColor("#880000")  # taxi
                taxipos.setProp(FEATPROP.MARK.value, "taxi")
                taxipos.setProp("_taxiways", vid)
                fc.append(taxipos)
            fc[-1].setProp(FEATPROP.MARK.value, "taxi end vertex")
        else:
            logger.warning(":taxi:out: no taxi route found")

        taxiendpos = MovePoint(geometry=taxi_end[0]["geometry"], properties=taxi_end[0]["properties"])
        taxiendpos.setSpeed(TAXI_SPEED)
        taxiendpos.setColor("#880088")  # parking
        taxiendpos.setProp(FEATPROP.MARK.value, "taxi end")
        fc.append(taxiendpos)

        takeoffholdpos = MovePoint(geometry=self.takeoff_hold["geometry"], properties=self.takeoff_hold["properties"])
        takeoffholdpos.setSpeed(0)
        takeoffholdpos.setColor("#880088")  # parking
        takeoffholdpos.setProp(FEATPROP.MARK.value, "takeoff hold")
        fc.append(takeoffholdpos)

        if show_pos:
            logger.debug(":taxi:out: taxi end: %s" % takeoffholdpos)
        else:
            rwy_name = self.flight.runway.name if self.flight.runway is not None else "no runway"
            logger.debug(":taxi:out: taxi end: holding for runway %s" % rwy_name)

        self.taxipos = fc
        logger.debug(":taxi:out: taxi %d moves" % (len(self.taxipos)))

        return (True, "DepartureMove::taxi completed")
