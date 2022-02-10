"""
A succession of positions where the aircraft passes. Includes taxi and takeoff or landing and taxi.
"""
import os
import json
import logging
from math import pi
from datetime import timedelta
from typing import Union
import copy

from geojson import Point, LineString, FeatureCollection
from turfpy.measurement import distance, destination, bearing

from ..flight import Flight
from ..airspace import Restriction
from ..airport import AirportBase
from ..aircraft import ACPERF
from ..geo import FeatureWithProps, moveOn, cleanFeatures, printFeatures
from ..utils import FT
from ..constants import POSITION_COLOR, FEATPROP, TAKEOFF_QUEUE_SIZE, TAXI_SPEED, SLOW_SPEED
from ..constants import FLIGHT_DATABASE, FLIGHT_PHASE
from ..parameters import AODB_DIR

from .standardturn import standard_turn_flyby

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
        if type(flight).__name__ == "Arrival":
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

        status = self.interpolate()
        if not status[0]:
            logger.warning(status[1])
            return status

        status = self.taxi()
        if not status[0]:
            logger.warning(status[1])
            return status

        printFeatures(self.taxipos, "after taxi")

        status = self.time()
        if not status[0]:
            logger.warning(status[1])
            return status

        return (True, "Movement::make completed")


    def save(self):
        """
        Save flight paths to 3 files for flight plan, detailed movement, and taxi path.
        Save a technical json file which can be loaded later, and GeoJSON files for display.
        @todo should save file format version number.
        """
        basename = os.path.join(AODB_DIR, FLIGHT_DATABASE, self.flight_id)

        def saveMe(arr, name):
            filename = os.path.join(basename + "-" + name + ".json")
            with open(filename, "w") as fp:
                json.dump(arr, fp, indent=4)

            filename = os.path.join(basename + "-" + name + ".geojson")
            with open(filename, "w") as fp:
                json.dump(FeatureCollection(features=cleanFeatures(arr)), fp, indent=4)

        saveMe(self.moves, "plan")
        saveMe(self.moves_st, "move")
        saveMe(self.taxipos, "taxi")

        logger.debug(":loadAll: saved %s" % self.flight_id)
        return (True, "Movement::save saved")


    def load(self):
        """
        Load flight paths from 3 files for flight plan, detailed movement, and taxi path.
        File must be saved by above save() function.
        """
        basename = os.path.join(DATA_DIR, FLIGHT_DATABASE, self.flight_id)

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

        def moveOnCP(fc, fcidx, currpos, alt):
            p, i = moveOn(fc, fcidx, currpos, alt)
            return (MovePoint(geometry=p["geometry"], properties=p["properties"]), i)

        def addCurrentPoint(coll, pos, oi, ni, reverse: bool = False):
            # logger.debug(":addCurrentPoint: %d %d %s" % (oi, ni, reverse))
            if oi != ni:
                for idx in range(oi+1, ni+1):
                    i = idx if not reverse else len(self.flight.flightplan_cp) - idx - 1
                    wpt = self.flight.flightplan_cp[i]
                    p = MovePoint(geometry=wpt["geometry"], properties=wpt["properties"])
                    currpos.setProp(FEATPROP.FLIGHT_PLAN_INDEX.value, i)
                    p.setColor("#ff0000") # flight plan point in RED
                    #@todo: will need to interpolate alt and speed for these points
                    coll.append(p)
                    # logger.debug(":addCurrentPoint: adding flight plan point: %d %s (%d)" % (i, wpt.getProp("_plan_segment_type"), len(coll)))
            pos.setColor("#00ff00")  # remarkable point in FREEN
            coll.append(pos)
            # logger.debug(":addCurrentPoint: adding remarkable point: %s (%d)" % (pos.getProp(FEATPROP.MARK), len(coll)))
            return ni

        fc = self.flight.flightplan_cp
        ac = self.flight.aircraft
        actype = ac.actype
        # actype.perfs()
        logger.debug(":vnav: %s: %d points in flight plan" % (type(self).__name__, len(fc)))

        # for f in self.flight.flightplan_cp:
        #     logger.debug(":vnav: flight plan: %s" % (f.getProp("_plan_segment_type")))

        # PART 1: (FORWARD): From takeoff to top of ascent
        #
        #
        logger.debug("DEPARTURE **********")
        groundmv = 0
        fcidx = 0

        if type(self).__name__ == "DepartureMove": # take off
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

            currpos = MovePoint(geometry=takeoff_hold["geometry"], properties={})
            currpos.setAltitude(alt)
            currpos.setSpeed(actype.getSI(0))
            currpos.setVSpeed(0)
            currpos.setColor(POSITION_COLOR.TAKEOFF_HOLD.value)
            currpos.setProp(FEATPROP.MARK.value, FLIGHT_PHASE.TAKEOFF_HOLD.value)
            currpos.setProp(FEATPROP.FLIGHT_PLAN_INDEX.value, 0)
            self.moves.append(currpos)
            self.takeoff_hold = copy.deepcopy(currpos)  # we keep this special position for taxiing (end_of_taxi)
            logger.debug(":vnav: takeoff hold at %s, %f" % (rwy.name, TOH_BLASTOFF))

            takeoff_distance = actype.getSI(ACPERF.takeoff_distance) * self.airport.runwayIsWet() / 1000  # must be km for destination()
            takeoff = destination(takeoff_hold, takeoff_distance, brg, {"units": "km"})

            currpos = MovePoint(geometry=takeoff["geometry"], properties={})
            currpos.setAltitude(alt)
            currpos.setSpeed(actype.getSI(ACPERF.takeoff_speed))
            currpos.setVSpeed(actype.getSI(ACPERF.initial_climb_speed))
            currpos.setColor(POSITION_COLOR.TAKE_OFF.value)
            currpos.setProp(FEATPROP.MARK.value, FLIGHT_PHASE.TAKE_OFF.value)
            currpos.setProp(FEATPROP.FLIGHT_PLAN_INDEX.value, 0)
            self.moves.append(currpos)
            groundmv = takeoff_distance
            logger.debug(":vnav: takeoff at %s, %f" % (rwy.name, takeoff_distance))

            # initial climb, commonly accepted to above 1500ft AGL
            logger.debug(":vnav: initialClimb")
            step = actype.initialClimb(alt)  # (t, d, altend)
            initial_climb_distance = step[1] / 1000  # km
            # find initial climb point

            # we climb on path to see if we reach indices...
            currpos, newidx = moveOnCP(fc, fcidx, currpos, initial_climb_distance)

            # we ignore currpos for now, we will climb straight...
            initial_climb = destination(takeoff, initial_climb_distance, brg, {"units": "km"})
            currpos = MovePoint(geometry=initial_climb["geometry"], properties={})
            currpos.setAltitude(alt)
            currpos.setSpeed(actype.getSI(ACPERF.initial_climb_speed))
            currpos.setVSpeed(actype.getSI(ACPERF.initial_climb_vspeed))
            currpos.setColor(POSITION_COLOR.INITIAL_CLIMB.value)
            currpos.setProp(FEATPROP.MARK.value, "end_initial_climb")
            currpos.setProp(FEATPROP.FLIGHT_PLAN_INDEX.value, newidx)
            self.moves.append(currpos)
            logger.debug(":vnav: initial climb end at %d, %f" % (newidx, initial_climb_distance))
            fcidx = newidx
            groundmv = groundmv + initial_climb_distance

        else: # ArrivalMove, simpler departure
            # Someday, we could add SID departure from runway for remote airport as well
            # Get METAR at airport, determine runway, select random runway & SID
            deptapt = fc[0]
            alt = deptapt.altitude()
            if alt is None:
                logger.warning(":vnav: departure airport has no altitude: %s" % deptapt)
                alt = 0
            currpos = MovePoint(geometry=deptapt["geometry"], properties=deptapt["properties"])
            currpos.setSpeed(actype.getSI(ACPERF.takeoff_speed))
            currpos.setColor(POSITION_COLOR.TAKE_OFF.value)
            currpos.setProp(FEATPROP.MARK.value, "origin")
            currpos.setProp(FEATPROP.FLIGHT_PLAN_INDEX.value, fcidx)
            self.moves.append(currpos)
            logger.debug(":vnav: origin added first point")

            # initial climb, commonly accepted to above 1500ft AGL
            logger.debug(":vnav: initialClimb")
            step = actype.initialClimb(alt)  # (t, d, altend)
            # find initial climb point
            groundmv = step[1]
            currpos, newidx = moveOnCP(fc, fcidx, currpos, step[1])
            currpos.setAltitude(step[2])
            currpos.setSpeed(actype.getSI(ACPERF.initial_climb_speed))
            currpos.setVSpeed(actype.getSI(ACPERF.initial_climb_vspeed))
            currpos.setColor(POSITION_COLOR.INITIAL_CLIMB.value)
            currpos.setProp(FEATPROP.MARK.value, FLIGHT_PHASE.INITIAL_CLIMB.value)  # end of it
            fcidx = addCurrentPoint(self.moves, currpos, fcidx, newidx)

        logger.debug(":vnav: climbToFL100")
        step = actype.climbToFL100(currpos.altitude())  # (t, d, altend)
        groundmv = groundmv + step[1]
        currpos, newidx = moveOnCP(fc, fcidx, currpos, step[1])
        currpos.setAltitude(step[2])
        currpos.setSpeed(actype.fl100Speed())
        currpos.setVSpeed(actype.getSI(ACPERF.climbFL150_vspeed))
        currpos.setColor(POSITION_COLOR.CLIMB.value)
        currpos.setProp(FEATPROP.MARK.value, "end_fl100_climb")
        fcidx = addCurrentPoint(self.moves, currpos, fcidx, newidx)

        # climb to cruise altitude
        cruise_speed = actype.getSI(ACPERF.cruise_mach)

        if self.flight.flight_level >= 150:
            logger.debug(":vnav: climbToFL150")
            step = actype.climbToFL240(currpos.altitude())  # (t, d, altend)
            groundmv = groundmv + step[1]
            currpos, newidx = moveOnCP(fc, fcidx, currpos, step[1])
            currpos.setAltitude(step[2])
            currpos.setSpeed(actype.getSI(ACPERF.climbFL150_speed))
            currpos.setVSpeed(actype.getSI(ACPERF.climbFL150_vspeed))
            currpos.setColor(POSITION_COLOR.CLIMB.value)
            currpos.setProp(FEATPROP.MARK.value, "end_fl150_climb")
            fcidx = addCurrentPoint(self.moves, currpos, fcidx, newidx)

            if self.flight.flight_level >= 240:
                logger.debug(":vnav: climbToFL240")
                step = actype.climbToFL240(currpos.altitude())  # (t, d, altend)
                groundmv = groundmv + step[1]
                currpos, newidx = moveOnCP(fc, fcidx, currpos, step[1])
                currpos.setAltitude(step[2])
                currpos.setSpeed(actype.getSI(ACPERF.climbFL240_speed))
                currpos.setVSpeed(actype.getSI(ACPERF.climbFL240_vspeed))
                currpos.setColor(POSITION_COLOR.CLIMB.value)
                currpos.setProp(FEATPROP.MARK.value, "end_fl240_climb")
                fcidx = addCurrentPoint(self.moves, currpos, fcidx, newidx)

                if self.flight.flight_level > 240:
                    logger.debug(":vnav: climbToCruise")
                    step = actype.climbToCruise(currpos.altitude(), self.flight.getCruiseAltitude())  # (t, d, altend)
                    groundmv = groundmv + step[1]
                    currpos, newidx = moveOnCP(fc, fcidx, currpos, step[1])
                    currpos.setAltitude(step[2])
                    currpos.setSpeed(actype.getSI(ACPERF.climbmach_mach))
                    currpos.setVSpeed(actype.getSI(ACPERF.climbmach_vspeed))
                    currpos.setProp(FEATPROP.MARK.value, FLIGHT_PHASE.TOP_OF_ASCENT.value)
                    currpos.setColor(POSITION_COLOR.TOP_OF_ASCENT.value)
                    fcidx = addCurrentPoint(self.moves, currpos, fcidx, newidx)
                    # cruise speed defaults to ACPERF.cruise_mach, we don't need to specify it
            else:
                logger.debug(":vnav: climbToCruise below FL240")
                step = actype.climbToCruise(currpos.altitude(), self.flight.getCruiseAltitude())  # (t, d, altend)
                groundmv = groundmv + step[1]
                currpos, newidx = moveOnCP(fc, fcidx, currpos, step[1])
                currpos.setAltitude(step[2])
                currpos.setSpeed(actype.getSI(ACPERF.climbFL240_speed))
                currpos.setVSpeed(actype.getSI(ACPERF.climbFL240_vspeed))
                currpos.setProp(FEATPROP.MARK.value, FLIGHT_PHASE.TOP_OF_ASCENT.value)
                currpos.setColor(POSITION_COLOR.TOP_OF_ASCENT.value)
                fcidx = addCurrentPoint(self.moves, currpos, fcidx, newidx)
                cruise_speed = (actype.getSI(ACPERF.climbFL240_speed) + actype.getSI(ACPERF.cruise_mach))/ 2
                logger.warning(":vnav: cruise speed below FL240: %f m/s" % (cruise_speed))
        else:
            logger.debug(":vnav: climbToCruise below FL150")
            step = actype.climbToCruise(currpos.altitude(), self.flight.getCruiseAltitude())  # (t, d, altend)
            groundmv = groundmv + step[1]
            currpos, newidx = moveOnCP(fc, fcidx, currpos, step[1])
            currpos.setAltitude(step[2])
            currpos.setSpeed(actype.getSI(ACPERF.climbFL240_speed))
            currpos.setVSpeed(actype.getSI(ACPERF.climbFL240_vspeed))
            currpos.setProp(FEATPROP.MARK.value, FLIGHT_PHASE.TOP_OF_ASCENT.value)
            currpos.setColor(POSITION_COLOR.TOP_OF_ASCENT.value)
            fcidx = addCurrentPoint(self.moves, currpos, fcidx, newidx)
            logger.warning(":vnav: cruise speed below FL150: %f m/s" % (cruise_speed))
            cruise_speed = (actype.getSI(ACPERF.climbFL150_speed) + actype.getSI(ACPERF.cruise_mach))/ 2

        # accelerate to cruise speed smoothly
        acceldist = 5000  # we reach cruise speed after 5km horizontal flight
        logger.debug(":vnav: accelerate to cruise speed")
        currpos, newidx = moveOnCP(fc, fcidx, currpos, acceldist)
        groundmv = groundmv + acceldist
        currpos.setAltitude(step[2])
        currpos.setSpeed(cruise_speed)
        currpos.setVSpeed(0)
        currpos.setColor(POSITION_COLOR.CRUISE.value)
        currpos.setProp(FEATPROP.MARK.value, "reached_cruise_speed")
        fcidx = addCurrentPoint(self.moves, currpos, fcidx, newidx)

        top_of_ascent_idx = fcidx + 1 # we reach top of ascent between idx and idx+1, so we cruise from idx+1 on.
        logger.debug(":vnav: cruise at %d after %f" % (top_of_ascent_idx, groundmv))
        logger.debug(":vnav: ascent added (+%d %d)" % (len(self.moves), len(self.moves)))
        # cruise until top of descent

        # PART 2: (REVERSE): From brake on runway to top of descent
        #
        #
        logger.debug("ARRIVAL **********")
        FINAL_ALT = 1000*FT
        APPROACH_ALT = 3000*FT
        STAR_ALT = 6000*FT

        revmoves = []
        groundmv = 0
        fc = self.flight.flightplan_cp.copy()
        fc.reverse()
        fcidx = 0

        # for f in fc:
        #     logger.debug(":vnav: flight plan reversed: %s" % (f.getProp("_plan_segment_type")))

        if type(self).__name__ == "ArrivalMove": # the path starts at the END of the departure runway
            LAND_TOUCH_DOWN = 0.4  # km
            rwy = self.flight.runway
            rwy_threshold = rwy.getPoint()
            alt = rwy_threshold.altitude()
            if alt is None:
                logger.warning(":vnav: departure airport has no altitude: %s" % rwy_threshold)
                alt = 0

            brg = bearing(rwy_threshold, rwy.end.getPoint())
            touch_down = destination(rwy_threshold, LAND_TOUCH_DOWN, brg, {"units": "km"})
            logger.debug(":vnav: arrival runway %s, %f" % (rwy.name, brg))

            # First point is where stopped
            rollout_distance = actype.getSI(ACPERF.landing_distance) * self.airport.runwayIsWet() / 1000 # must be km for destination()
            landing = destination(touch_down, rollout_distance, brg, {"units": "km"})

            currpos = MovePoint(geometry=landing["geometry"], properties={})
            currpos.setAltitude(alt)
            currpos.setSpeed(TAXI_SPEED)
            currpos.setVSpeed(0)
            currpos.setColor(POSITION_COLOR.ROLL_OUT.value)
            currpos.setProp(FEATPROP.MARK.value, "end_rollout")
            currpos.setProp(FEATPROP.FLIGHT_PLAN_INDEX.value, 0)
            revmoves.append(currpos)
            logger.debug(":vnav: stopped at %s, %f" % (rwy.name, rollout_distance))
            self.end_rollout = copy.deepcopy(currpos)  # we keep this special position for taxiing (start_of_taxi)

            # Point before is touch down
            currpos = MovePoint(geometry=touch_down["geometry"], properties={})
            currpos.setAltitude(alt)
            currpos.setSpeed(actype.getSI(ACPERF.landing_speed))
            currpos.setVSpeed(0)
            currpos.setColor(POSITION_COLOR.TOUCH_DOWN.value)
            currpos.setProp(FEATPROP.MARK.value, FLIGHT_PHASE.TOUCH_DOWN.value)
            currpos.setProp(FEATPROP.FLIGHT_PLAN_INDEX.value, 0)
            revmoves.append(currpos)
            logger.debug(":vnav: touch down at %s, %f" % (rwy.name, LAND_TOUCH_DOWN))

        else:
            # Someday, we could add STAR/APPCH to runway for remote airport as well
            # Get METAR at airport, determine runway, select random RWY, STAR and APPCH
            arrvapt = fc[fcidx]
            alt = arrvapt.altitude()
            if alt is None:
                logger.warning(":vnav: arrival airport has no altitude: %s" % arrvapt)
                alt = 0

            currpos = MovePoint(geometry=arrvapt["geometry"], properties=arrvapt["properties"])
            currpos.setProp(FEATPROP.MARK.value, "destination")
            currpos.setSpeed(actype.getSI(ACPERF.landing_speed))
            currpos.setProp(FEATPROP.FLIGHT_PLAN_INDEX.value, len(fc) - fcidx)
            currpos.setColor(POSITION_COLOR.DESTINATION.value)
            revmoves.append(currpos)
            logger.debug(":vnav: destination added last point")

        # we move to the final fix at max 3000ft, approach speed
        logger.debug(":vnav: final")
        step = actype.descentFinal(alt+APPROACH_ALT, alt)  # (t, d, altend)
        groundmv = groundmv + step[1]
        # find initial climb point
        currpos, newidx = moveOnCP(fc, fcidx, currpos, step[1])
        currpos.setAltitude(alt+APPROACH_ALT)
        currpos.setSpeed(actype.getSI(ACPERF.landing_speed))  # approach speed?
        currpos.setVSpeed(actype.getSI(ACPERF.approach_vspeed))
        currpos.setColor(POSITION_COLOR.FINAL.value)
        currpos.setProp(FEATPROP.MARK.value, "start_of_final")
        currpos.setProp(FEATPROP.FLIGHT_PLAN_INDEX.value, fcidx)
        fcidx = addCurrentPoint(revmoves, currpos, fcidx, newidx, True)


        # i = 0
        # for f in fc:
        #     logger.debug(":vnav: flight plan last at %d %s" % (i, f.id))
        #     # logger.debug(":vnav: revmoves at %d %s" % (i, f))
        #     i = i + 1

        # go at APPROACH_ALT at first point of approach / last point of star
        if type(self).__name__ == "ArrivalMove":

            # find first point of approach:
            k = len(fc) - 1
            while fc[k].getProp("_plan_segment_type") != "appch" and k > 0:
                k = k - 1
            if k == 0:
                logger.warning(":vnav: no approach found")
            else:
                logger.debug(":vnav: start of approach at index %d, %s" % (k, fc[k].getProp("_plan_segment_type")))
                if k <= fcidx:
                    logger.debug(":vnav: final fix seems further away than start of apprach")
                else:
                    logger.debug(":vnav: flight level to final fix")
                    # add all approach points between start to approach to final fix
                    for i in range(fcidx+1, k):
                        wpt = fc[i]
                        # logger.debug(":vnav: APPCH: flight level: %d %s" % (i, wpt.getProp("_plan_segment_type")))
                        p = MovePoint(geometry=wpt["geometry"], properties=wpt["properties"])
                        p.setAltitude(alt+APPROACH_ALT)
                        p.setSpeed(actype.getSI(ACPERF.approach_speed))
                        p.setVSpeed(0)
                        p.setColor("#ff00ff")  # approach in MAGENTA
                        p.setProp(FEATPROP.MARK.value, "approach")
                        p.setProp(FEATPROP.FLIGHT_PLAN_INDEX.value, i)
                        revmoves.append(p)
                        # logger.debug(":vnav: adding remarkable point: %d %s (%d)" % (i, p.getProp(FEATPROP.MARK), len(revmoves)))

                    # i = 0
                    # for f in revmoves:
                    #     a = f.altitude()
                    #     s = f.speed()
                    #     logger.debug(":vnav: revmoves before last at %d %s %s: %f %f" % (i, f.getProp(FEATPROP.MARK), f.getProp("_plan_segment_type"), s if s is not None else -1, a if a is not None else -1))
                    #     # logger.debug(":vnav: revmoves at %d %s" % (i, f))
                    #     i = i + 1

                    # add start of approach
                    currpos = MovePoint(geometry=fc[k]["geometry"], properties=fc[k]["properties"])
                    currpos.setAltitude(alt+APPROACH_ALT)
                    currpos.setSpeed(actype.getSI(ACPERF.approach_speed))
                    currpos.setVSpeed(0)
                    currpos.setProp(FEATPROP.MARK.value, "start_of_approach")
                    currpos.setProp(FEATPROP.FLIGHT_PLAN_INDEX.value, k)
                    currpos.setColor("#880088")  # approach in MAGENTA
                    revmoves.append(currpos)
                    # logger.debug(":vnav: adding remarkable point: %d %s (%d)" % (k, currpos.getProp(FEATPROP.MARK), len(revmoves)))

                    fcidx = k

                    # i = 0
                    # for f in revmoves:
                    #     a = f.altitude()
                    #     s = f.speed()
                    #     logger.debug(":vnav: revmoves at %d %s %s: %f %f" % (i, f.getProp(FEATPROP.MARK), f.getProp("_plan_segment_type"), s if s is not None else -1, a if a is not None else -1))
                    #     # logger.debug(":vnav: revmoves at %d %s" % (i, f))
                    #     i = i + 1

            # find first point of star:
            k = len(fc) - 1
            while fc[k].getProp("_plan_segment_type") != "star" and k > 0:
                k = k - 1
            if k == 0:
                logger.warning(":vnav: no star found")
            else:
                logger.debug(":vnav: start of star at index %d, %s" % (k, fc[k].getProp("_plan_segment_type")))
                if k <= fcidx:
                    logger.debug(":vnav: final fix seems further away than start of star")
                else:
                    logger.debug(":vnav: flight level to start of approach")
                    # add all approach points between start to approach to final fix
                    for i in range(fcidx+1, k):
                        wpt = fc[i]
                        # logger.debug(":vnav: STAR: flight level: %d %s" % (i, wpt.getProp("_plan_segment_type")))
                        p = MovePoint(geometry=wpt["geometry"], properties=wpt["properties"])
                        p.setAltitude(alt+STAR_ALT)
                        p.setSpeed(actype.getSI(ACPERF.approach_speed))
                        p.setVSpeed(0)
                        p.setColor("#ff00ff")  # star in MAGENTA
                        p.setProp(FEATPROP.MARK.value, "star")
                        p.setProp(FEATPROP.FLIGHT_PLAN_INDEX.value, i)
                        revmoves.append(p)
                        # logger.debug(":vnav: adding remarkable point: %d %s (%d)" % (i, p.getProp(FEATPROP.MARK), len(revmoves)))
                    # add start of approach
                    #
                    # @todo:
                    # we assume start of star is where holding occurs
                    # Add holding pattern
                    self.holdingpoint = fc[k].id
                    logger.debug(":vnav: holding at : %s" % (self.holdingpoint))
                    currpos = MovePoint(geometry=fc[k]["geometry"], properties=fc[k]["properties"])
                    currpos.setAltitude(alt+STAR_ALT)
                    currpos.setSpeed(actype.getSI(ACPERF.approach_speed))
                    currpos.setVSpeed(0)
                    currpos.setProp(FEATPROP.MARK.value, "start_of_star")
                    currpos.setProp(FEATPROP.FLIGHT_PLAN_INDEX.value, k)
                    currpos.setColor("#ff00ff")  # star in MAGENTA
                    revmoves.append(currpos)
                    # logger.debug(":vnav: adding remarkable point: %d %s (%d)" % (k, currpos.getProp(FEATPROP.MARK), len(revmoves)))
                    fcidx = k

        if self.flight.flight_level > 100:
            # descent from FL100 to first approach point
            logger.debug(":vnav: descent to star alt")
            step = actype.descentApproach(10000*FT, alt+STAR_ALT)  # (t, d, altend)
            groundmv = groundmv + step[1]
            currpos, newidx = moveOnCP(fc, fcidx, currpos, step[1])
            currpos.setAltitude(10000*FT)
            currpos.setSpeed(actype.getSI(ACPERF.approach_speed))
            currpos.setVSpeed(actype.getSI(ACPERF.approach_vspeed))
            currpos.setProp(FEATPROP.MARK.value, "descent_fl100_reached")
            fcidx = addCurrentPoint(revmoves, currpos, fcidx, newidx, True)

            if self.flight.flight_level > 240:
                # descent from FL240 to FL100
                logger.debug(":vnav: descent to FL100")
                step = actype.descentToFL100(24000*FT)  # (t, d, altend)
                groundmv = groundmv + step[1]
                currpos, newidx = moveOnCP(fc, fcidx, currpos, step[1])
                currpos.setAltitude(24000*FT)
                currpos.setSpeed(actype.getSI(ACPERF.descentFL100_speed))
                currpos.setVSpeed(actype.getSI(ACPERF.descentFL100_vspeed))
                currpos.setProp(FEATPROP.MARK.value, "descent_fl240_reached")
                fcidx = addCurrentPoint(revmoves, currpos, fcidx, newidx, True)

                if self.flight.flight_level > 240:
                    # descent from cruise above FL240 to FL240
                    logger.debug(":vnav: descent to FL240")
                    step = actype.descentToFL240(self.flight.getCruiseAltitude())  # (t, d, altend)
                    groundmv = groundmv + step[1]
                    currpos, newidx = moveOnCP(fc, fcidx, currpos, step[1])
                    currpos.setAltitude(self.flight.getCruiseAltitude())
                    currpos.setSpeed(actype.getSI(ACPERF.descentFL240_mach))
                    currpos.setVSpeed(actype.getSI(ACPERF.descentFL240_vspeed))
                    currpos.setProp(FEATPROP.MARK.value, "top_of_descent")
                    fcidx = addCurrentPoint(revmoves, currpos, fcidx, newidx, True)
            else:
                # descent from cruise below FL240 to FL100
                logger.debug(":vnav: descent from under FL240 to FL100")
                step = actype.descentToFL100(self.flight.getCruiseAltitude())  # (t, d, altend)
                groundmv = groundmv + step[1]
                currpos, newidx = moveOnCP(fc, fcidx, currpos, step[1])
                currpos.setAltitude(self.flight.getCruiseAltitude())
                currpos.setSpeed(actype.getSI(ACPERF.descentFL100_speed))
                currpos.setVSpeed(actype.getSI(ACPERF.descentFL100_vspeed))
                currpos.setProp(FEATPROP.MARK.value, "top_of_descent")  # !
                fcidx = addCurrentPoint(revmoves, currpos, fcidx, newidx, True)
        else:
            # descent from cruise below FL100 to approach alt
            logger.debug(":vnav: descent from under FL100 to approach alt")
            step = actype.descentApproach(self.flight.getCruiseAltitude(), alt+APPROACH_ALT)  # (t, d, altend)
            groundmv = groundmv + step[1]
            currpos, newidx = moveOnCP(fc, fcidx, currpos, step[1])
            currpos.setAltitude(self.flight.getCruiseAltitude())
            currpos.setSpeed(actype.getSI(ACPERF.approach_speed))
            currpos.setVSpeed(actype.getSI(ACPERF.approach_vspeed))
            currpos.setProp(FEATPROP.MARK.value, "top_of_descent")  # !
            fcidx = addCurrentPoint(revmoves, currpos, fcidx, newidx, True)

        # decelerate to descent speed smoothly
        acceldist = 5000  # we reach cruise speed after 5km horizontal flight
        logger.debug(":vnav: decelerate from cruise speed to first descent speed (which depends on alt...)")
        currpos, newidx = moveOnCP(fc, fcidx, currpos, acceldist)
        groundmv = groundmv + acceldist
        currpos.setAltitude(self.flight.getCruiseAltitude())
        currpos.setSpeed(cruise_speed)  # computed when climbing
        currpos.setVSpeed(0)
        currpos.setProp(FEATPROP.MARK.value, "end_of_cruise_speed")
        fcidx = addCurrentPoint(revmoves, currpos, fcidx, newidx, True)

        top_of_decent_idx = fcidx + 1 # we reach top of descent between idx and idx+1, so we cruise until idx+1
        logger.debug(":vnav: reverse descent at %d after %f" % (top_of_decent_idx, groundmv))
        # we .reverse() array:
        top_of_decent_idx = len(self.flight.flightplan_cp) - top_of_decent_idx  - 1
        logger.debug(":vnav: cruise until %d, descent after %d, remains %f to destination" % (top_of_decent_idx, top_of_decent_idx, groundmv))

        # for f in revmoves:
        #     a = f.altitude()
        #     s = f.speed()
        #     logger.debug(":vnav: revmoves at %s %s: %f %f" % (f.getProp(FEATPROP.MARK), f.getProp("_plan_segment_type"), s if s is not None else -1, a if a is not None else -1))

        # PART 3: Join top of ascent to top of descent at cruise speed
        #
        # We copy waypoints from start of cruise to end of cruise
        logger.debug("CRUISE **********")
        if top_of_decent_idx > top_of_ascent_idx:
            # logger.debug(":vnav: adding cruise: %d -> %d" % (top_of_ascent_idx, top_of_decent_idx))
            for i in range(top_of_ascent_idx, top_of_decent_idx):
                wpt = self.flight.flightplan_cp[i]
                # logger.debug(":vnav: adding cruise: %d %s" % (i, wpt.getProp("_plan_segment_type")))
                p = MovePoint(geometry=wpt["geometry"], properties=wpt["properties"])
                p.setAltitude(self.flight.getCruiseAltitude())
                p.setSpeed(cruise_speed)
                p.setColor("#0000ff")  # Cruise in BLUE
                p.setProp(FEATPROP.MARK.value, "cruise")
                p.setProp(FEATPROP.FLIGHT_PLAN_INDEX.value, i)
                self.moves.append(p)
            logger.debug(":vnav: cruise added (+%d %d)" % (top_of_decent_idx - top_of_ascent_idx, len(self.moves)))
        else:
            logger.warning(":vnav: cruise too short (%d -> %d)" % (top_of_ascent_idx, top_of_decent_idx))

        # PART 4: Add descent and final
        #
        #
        revmoves.reverse()
        self.moves = self.moves + revmoves
        logger.debug(":vnav: descent added (+%d %d)" % (len(revmoves), len(self.moves)))

        return (True, "Movement::vnav completed without restriction")


    def standard_turns(self):
        def turnRadius(speed): # speed in m/s, returns radius in m
            return 120 * speed / (2 * pi)

        self.moves_st = []
        last_speed = 100
        # Add first point
        self.moves_st.append(self.moves[0])

        for i in range(1, len(self.moves) - 1):
            li = LineString([self.moves[i-1]["geometry"]["coordinates"], self.moves[i]["geometry"]["coordinates"]])
            lo = LineString([self.moves[i]["geometry"]["coordinates"], self.moves[i+1]["geometry"]["coordinates"]])
            s = last_speed  # arrin[i].speed()
            if s is None:
                s = last_speed
            arc = standard_turn_flyby(li, lo, turnRadius(s))
            last_speed = s

            if arc is not None:
                self.moves_st.append(self.moves[i])
                for p in arc:
                    self.moves_st.append(MovePoint(geometry=p["geometry"], properties=p["properties"]))
            else:
                self.moves_st.append(self.moves[i])
        # Add last point too
        self.moves_st.append(self.moves[-1])
        return (True, "Movement::standard_turns added")


    def taxi(self):
        return (False, "Movement::taxi not implemented")


    def interpolate(self):
        """
        Compute interpolated values for altitude and speed based on distance.
        This is a simple linear interpolation based on distance between points.
        Runs for flight portion of flight.
        """

        to_interp = self.moves_st if self.moves_st is not None else self.moves

        def interpolate_speed(istart, iend):
            speedstart = to_interp[istart].speed()  # first known speed
            speedend = to_interp[iend].speed()  # last known speed

            if speedstart == speedend: # simply copy
                for idx in range(istart, iend):
                    to_interp[idx].setSpeed(speedstart)
                return

            ratios = {}
            spdcumul = 0
            for idx in range(istart+1, iend):
                d = distance(to_interp[idx-1], to_interp[idx], "m")
                spdcumul = spdcumul + d
                ratios[idx] = spdcumul
            # logger.debug(":interpolate_speed: (%d)%f -> (%d)%f, %f" % (istart, speedstart, iend, speedend, spdcumul))
            speed_a = (speedend - speedstart) / spdcumul
            speed_b = speedstart
            for idx in range(istart+1, iend):
                # logger.debug(":interpolate_speed: %d %f %f" % (idx, ratios[idx]/spdcumul, speed_b + speed_a * ratios[idx]))
                to_interp[idx].setSpeed(speed_b + speed_a * ratios[idx] / spdcumul)

        def interpolate_altitude(istart, iend):
            altstart = to_interp[istart].altitude()  # first known alt
            altend = to_interp[iend].altitude()  # last known alt

            if altstart == altend: # simply copy
                for idx in range(istart, iend):
                    to_interp[idx].setAltitude(altstart)
                return

            ratios = {}
            altcumul = 0
            for idx in range(istart+1, iend+1):
                d = distance(to_interp[idx-1], to_interp[idx], "m")
                altcumul = altcumul + d
                ratios[idx] = altcumul
            # logger.debug(":interpolate_alt: (%d)%f -> (%d)%f, %f" % (istart, altstart, iend, altend, altcumul))
            alt_a = (altend - altstart) / altcumul
            alt_b = altstart
            for idx in range(istart+1, iend):
                # logger.debug(":interpolate_alt: %d %f %f" % (idx, ratios[idx]/altcumul, alt_b + alt_a * ratios[idx]))
                to_interp[idx].setAltitude(alt_b + alt_a * ratios[idx] / altcumul)

        # we do have a speed for first point in flight for both arrival (takeoff_speed, apt.alt) and departure (landing_speed, apt.alt)
        nospeed_idx = None  # index of last elem with not speed, elem[0] has speed.
        noalt_idx = None
        for idx in range(1, len(to_interp)):
            f = to_interp[idx]

            s = f.speed()
            if s is None:
                if nospeed_idx is None:
                    nospeed_idx = idx - 1
            else:
                if nospeed_idx is not None:
                    interpolate_speed(nospeed_idx, idx)
                    nospeed_idx = None

            a = f.altitude()
            if a is None:
                if noalt_idx is None:
                    noalt_idx = idx - 1
            else:
                if noalt_idx is not None:
                    interpolate_altitude(noalt_idx, idx)
                    noalt_idx = None

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

        elapsed = 0
        wpts = self.moves_st
        currpos = wpts[0]

        for idx in range(1, len(wpts)):
            nextpos = wpts[idx]
            d = distance(currpos, nextpos) * 1000 # km
            s = (nextpos.speed() + currpos.speed()) / 2
            t = d / s  # km
            elapsed = elapsed + t
            currpos.setTime(elapsed)
            currpos = nextpos

        # only show values of last iteration (can be moved inside loop)
        logger.debug(":time: %3d: %10.3fm at %5.1fm/s = %6.1fs, total=%s" % (idx, d, currpos.speed(), t, timedelta(seconds=elapsed)))

        return (True, "Movement::time computed")


    def taxiTime(self):
        """
        Time 0 is start of pushback (Departure) or end of roll out (Arrival).
        Last time is take off hold (Departure) or parking (Arrival).
        """
        return (False, "Movement::taxiTime not implemented")


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
        logger.debug(":taxi: taxi start: %s" % taxi_start)
        if taxi_start[0] is None:
            logger.warning(":taxi: could not find taxi start")
        taxistartpos = MovePoint(geometry=taxi_start[0]["geometry"], properties=taxi_start[0]["properties"])
        taxistartpos.setSpeed(TAXI_SPEED)
        taxistartpos.setColor("#880088")  # parking
        taxistartpos.setProp(FEATPROP.MARK.value, "taxi start")
        fc.append(taxistartpos)

        taxistart_vtx = self.airport.taxiways.nearest_vertex(taxi_start[0])
        logger.debug(":taxi: taxi start vtx: %s" % taxistart_vtx)
        if taxistart_vtx[0] is None:
            logger.warning(":taxi: could not find taxi start vertex")
        taxistartpos = MovePoint(geometry=taxistart_vtx[0]["geometry"], properties=taxistart_vtx[0]["properties"])
        taxistartpos.setSpeed(TAXI_SPEED)
        taxistartpos.setColor("#880088")  # parking
        taxistartpos.setProp(FEATPROP.MARK.value, "taxi start vertex")
        fc.append(taxistartpos)

        parking = self.airport.parkings[self.flight.ramp]
        logger.debug(":taxi: parking: %s" % parking)
        # we call the move from packing position to taxiway network the "parking entry"
        parking_entry = self.airport.taxiways.nearest_point_on_edge(parking)
        logger.debug(":taxi: parking_entry: %s" % parking_entry[0])

        if parking_entry[0] is None:
            logger.warning(":taxi: could not find parking entry")

        parkingentry_vtx = self.airport.taxiways.nearest_vertex(parking_entry[0])
        if parkingentry_vtx[0] is None:
            logger.warning(":taxi: could not find parking entry vertex")
        logger.debug(":taxi: parkingentry_vtx: %s " % parkingentry_vtx[0])

        taxi_ride = self.airport.taxiways.AStar(taxistart_vtx[0].id, parkingentry_vtx[0].id)
        logger.debug(":taxi: taxi_ride: %s -> %s: %s" % (taxistart_vtx[0].id, parkingentry_vtx[0].id, taxi_ride))

        dummy = self.airport.taxiways.AStar(parkingentry_vtx[0].id, taxistart_vtx[0].id)
        logger.debug(":taxi: taxi_ride inverted: %s -> %s: %s" % (taxistart_vtx[0].id, parkingentry_vtx[0].id, dummy))

        if taxi_ride is None and dummy is not None:
            logger.debug(":taxi: using taxi_ride inverted")
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
            logger.warning(":taxi: no taxi route found")

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

        self.taxipos = fc
        logger.debug(":taxi: taxi %d moves" % (len(self.taxipos)))

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
        fc = []

        parking = self.airport.parkings[self.flight.ramp]
        logger.debug(":taxi: parking: %s" % parking)
        parkingpos = MovePoint(geometry=parking["geometry"], properties=parking["properties"])
        parkingpos.setSpeed(0)
        parkingpos.setColor("#880088")  # parking
        parkingpos.setProp(FEATPROP.MARK.value, "parking")
        fc.append(parkingpos)

        # we call the move from packing position to taxiway network the "pushback"
        pushback_end = self.airport.taxiways.nearest_point_on_edge(parking)
        logger.debug(":taxi: pushback_end: %s" % pushback_end[0])
        if pushback_end[0] is None:
            logger.warning(":taxi: could not find pushback end")

        pushbackpos = MovePoint(geometry=pushback_end[0]["geometry"], properties=pushback_end[0]["properties"])
        pushbackpos.setSpeed(SLOW_SPEED)
        pushbackpos.setColor("#880088")  # parking
        pushbackpos.setProp(FEATPROP.MARK.value, "pushback")
        fc.append(pushbackpos)

        pushback_vtx = self.airport.taxiways.nearest_vertex(pushback_end[0])
        logger.debug(":taxi: pushback_vtx: %s" % pushback_vtx[0])
        if pushback_vtx[0] is None:
            logger.warning(":taxi: could not find pushback end vertex")

        last_vtx = pushback_vtx

        if TAKEOFF_QUEUE_SIZE > 0:
            # Taxi from pushback to start of queue
            #
            rwy = self.flight.runway

            queuepnt = self.airport.queue_point(rwy.name, 0)
            queuerwy = self.airport.taxiways.nearest_point_on_edge(queuepnt)
            logger.debug(":taxi: start of queue point: %s" % queuerwy[0])
            if queuerwy[0] is None:
                logger.warning(":taxi: could not find start of queue point")

            queuerwy_vtx = self.airport.taxiways.nearest_vertex(queuerwy[0])
            logger.debug(":taxi: queuerwy_vtx %s" % queuerwy_vtx[0])
            if queuerwy_vtx[0] is None:
                logger.warning(":taxi: could not find start of queue vertex")

            taxi_ride = self.airport.taxiways.AStar(pushback_vtx[0].id, queuerwy_vtx[0].id)
            logger.debug(":taxi: taxi_ride: %s -> %s: %s" % (pushback_vtx[0].id, queuerwy_vtx[0].id, taxi_ride))

            dummy = self.airport.taxiways.AStar(queuerwy_vtx[0].id, pushback_vtx[0].id)
            logger.debug(":taxi: taxi_ride inverted: %s -> %s: %s" % (queuerwy_vtx[0].id, pushback_vtx[0].id, dummy))

            if taxi_ride is None and dummy is not None:
                logger.debug(":taxi: using taxi_ride inverted")
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
                fc[-1].setProp(FEATPROP.MARK.value, "taxi start of queue")
            else:
                logger.warning(":taxi: no taxi route found")

            # Taxi from queue point 1 to last, stay on to taxiway edges
            #
            last_queue_on = None
            cnt = 0
            for i in range(1, len(self.airport.takeoff_queues[rwy.name])):
                queuepnt = self.airport.queue_point(rwy.name, i)
                queuerwy = self.airport.taxiways.nearest_point_on_edge(queuepnt)
                # logger.debug(":taxi: queue_point: %s" % queuerwy[0])
                if queuerwy[0] is None:
                    logger.warning(":taxi: could not place queue on taxiway")
                else:
                    last_queue_on = queuerwy
                    qspos = MovePoint(geometry=queuerwy[0]["geometry"], properties=queuerwy[0]["properties"])
                    qspos.setSpeed(TAXI_SPEED)
                    qspos.setColor("#880000")
                    qspos.setProp(FEATPROP.MARK.value, "queue %s" % i)
                    fc.append(qspos)
                    cnt = cnt + 1
            logger.warning(":taxi: added %d queue points" % cnt)

            if last_queue_on[0] is None:
                logger.warning(":taxi: could not find last queue point")
            else:
                last_queue_vtx = self.airport.taxiways.nearest_vertex(last_queue_on[0])
                if last_queue_vtx[0] is None:
                    # BIG PROBLEM IF POINT last_queue_on WAS ADDED AND CANNOT FIND VERTEX
                    logger.warning(":taxi: could not find last queue vertex")
                else:
                    last_vtx = last_queue_vtx

        # Taxi from end of queue to takeoff-hold
        #
        taxi_end = self.airport.taxiways.nearest_point_on_edge(self.takeoff_hold)
        logger.debug(":taxi: taxi_end: %s" % taxi_end[0])
        if taxi_end[0] is None:
            logger.warning(":taxi: could not find taxi end")

        taxiend_vtx = self.airport.taxiways.nearest_vertex(taxi_end[0])
        logger.debug(":taxi: taxiend_vtx %s" % taxiend_vtx[0])
        if taxiend_vtx[0] is None:
            logger.warning(":taxi: could not find taxi end vertex")

        taxi_ride = self.airport.taxiways.AStar(last_vtx[0].id, taxiend_vtx[0].id)
        logger.debug(":taxi: taxi_ride: %s -> %s: %s" % (last_vtx[0].id, taxiend_vtx[0].id, taxi_ride))

        dummy = self.airport.taxiways.AStar(taxiend_vtx[0].id, last_vtx[0].id)
        logger.debug(":taxi: taxi_ride inverted: %s -> %s: %s" % (taxiend_vtx[0].id, last_vtx[0].id, dummy))

        if taxi_ride is None and dummy is not None:
            logger.debug(":taxi: using taxi_ride inverted")
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
            logger.warning(":taxi: no taxi route found")

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

        self.taxipos = fc
        logger.debug(":taxi: taxi %d moves" % (len(self.taxipos)))

        return (True, "DepartureMove::taxi completed")