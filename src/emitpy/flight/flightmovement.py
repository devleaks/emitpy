"""
A succession of positions where the aircraft passes. Includes taxi and takeoff or landing and taxi.
"""
import os
import json
import logging
from math import pi
import copy

from geojson import LineString, FeatureCollection, Feature
from turfpy.measurement import distance, destination, bearing

from emitpy.flight import Flight
from emitpy.airport import ManagedAirportBase
from emitpy.aircraft import ACPERF
from emitpy.geo import MovePoint, Movement
from emitpy.geo import moveOn, cleanFeatures, findFeatures, asLineString, toKML
from emitpy.graph import Route
from emitpy.utils import FT, NAUTICAL_MILE
from emitpy.constants import POSITION_COLOR, FEATPROP, TAKE_OFF_QUEUE_SIZE, TAXI_SPEED, SLOW_SPEED
from emitpy.constants import FLIGHT_DATABASE, FLIGHT_PHASE, FILE_FORMAT, MOVE_TYPE
from emitpy.parameters import MANAGED_AIRPORT_AODB
from emitpy.message import FlightMessage

from emitpy.utils import interpolate as doInterpolation, compute_time as doTime
from .standardturn import standard_turn_flyby

logger = logging.getLogger("FlightMovement")


class FlightMovement(Movement):
    """
    Movement build the detailed path of the aircraft, both on the ground (taxi) and in the air,
    from takeoff to landing and roll out.
    """
    def __init__(self, flight: Flight, airport: ManagedAirportBase):
        Movement.__init__(self, airport=airport)
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
            "icao24": self.flight.getInfo()["icao24"]
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

        logger.debug(f"flight {len(self.moves)} points, taxi {len(self.taxipos)} points")
        return (True, "Movement::make completed")


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
            with open(filename, "w") as fp:
                json.dump(FeatureCollection(features=cleanFeatures(arr)), fp, indent=4)

        # saveMe(self.flight.flightplan_wpts, "1-plan")
        ls = Feature(geometry=asLineString(self.flight.flightplan_wpts))
        saveMe(self.flight.flightplan_wpts + [ls], FILE_FORMAT.FLIGHT_PLAN.value)

        # saveMe(self._premoves, "2-flight")
        ls = Feature(geometry=asLineString(self._premoves))
        saveMe(self._premoves + [ls], FILE_FORMAT.FLIGHT.value)

        # saveMe(self.moves, "3-move")
        ls = Feature(geometry=asLineString(self.moves))
        saveMe(self.moves + [ls], FILE_FORMAT.MOVE.value)

        # saveMe(self.taxipos, "4-taxi")
        ls = Feature(geometry=asLineString(self.taxipos))
        saveMe(self.taxipos + [ls], FILE_FORMAT.TAXI.value)

        filename = os.path.join(basename + FILE_FORMAT.MOVE.value + ".kml")
        with open(filename, "w") as fp:
            fp.write(self.getKML())
            logger.debug(f"saved kml {filename} ({len(self.moves)})")

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
            self.moves = json.load(fp)

        filename = os.path.join(basename, FILE_FORMAT.TAXI.value)
        with open(filename, "r") as fp:
            self.taxipos = json.load(fp)

        logger.debug("loaded %d " % self.flight_id)
        return (True, "Movement::load loaded")


    def getKML(self):
        return toKML(cleanFeatures(self.moves))


    def getMoves(self):
        # Your choice... moves? (default from super()) moves_st? includes standard turns
        return self.moves


    def vnav(self):
        """
        Perform vertical navigation for route
        @todo: Add optional hold
        """
        is_grounded = True

        def addCurrentpoint(coll, pos, oi, ni, color, mark, reverse: bool = False):
            # catch up adding all points in flight plan between oi, ni
            # then add pos (which is between ni and ni+1)
            # logger.debug("%d %d %s" % (oi, ni, reverse))
            if oi != ni:
                for idx in range(oi+1, ni+1):
                    i = idx if not reverse else len(self.flight.flightplan_wpts) - idx - 1
                    wpt = self.flight.flightplan_wpts[i]
                    p = MovePoint.new(wpt)
                    logger.debug(f"addCurrentpoint:{'(rev)' if reverse else ''} adding {p.getProp(FEATPROP.PLAN_SEGMENT_TYPE.value)} {p.getProp(FEATPROP.PLAN_SEGMENT_NAME.value)}")
                    p.setColor(color)
                    p.setProp(FEATPROP.MARK.value, mark)
                    p.setProp(FEATPROP.FLIGHT_PLAN_INDEX.value, i)
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
            newpos.setProp(FEATPROP.MARK.value, mark)
            return (newpos, addCurrentpoint(coll, newpos, fcidx, newidx, color, mark_tr, reverse))

        def addMovepoint(arr, src, alt, speed, vspeed, color, mark, ix):
            # create a copy of src, add properties on copy, and add copy to arr.
            # logger.debug(f"{mark} {ix}, s={speed}")
            mvpt = MovePoint(geometry=src["geometry"], properties={})
            mvpt.setAltitude(alt)
            mvpt.setSpeed(speed)
            mvpt.setVSpeed(vspeed)
            mvpt.setColor(color)
            mvpt.setProp(FEATPROP.MARK.value, mark)
            mvpt.setProp(FEATPROP.FLIGHT_PLAN_INDEX.value, ix)
            mvpt.setProp(FEATPROP.GROUNDED.value, is_grounded)
            arr.append(mvpt)
            return mvpt

        if self.flight.flightplan_wpts is None or len(self.flight.flightplan_wpts) == 0:
            logger.warning("no flight plan")
            return (False, "Movement::vnav no flight plan, cannot move")

        fc = self.flight.flightplan_wpts
        ac = self.flight.aircraft
        actype = ac.actype
        # actype.perfs()
        logger.debug(f"{'*' * 30} {type(self).__name__}: {len(fc)} points in flight plan {'*' * 30}")

        # for f in self.flight.flightplan_wpts:
        #     logger.debug("flight plan: %s" % (f.getProp(FEATPROP.PLAN_SEGMENT_TYPE.value)))

        # PART 1: FORWARD: From takeoff to top of ascent
        #
        #
        logger.debug(f"departure from {self.flight.departure.icao} " + "=" * 30)
        TOH_BLASTOFF = 0.2  # km, distance of take-off hold position from runway threshold
        groundmv = 0
        fcidx = 0
        rwy = None

        if self.flight.departure.has_rwys():  # take off self.flight.is_departure()
            if self.flight.is_departure():    # we are at the managed airport, we must use the selected runway
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
            takeoff_hold = destination(rwy_threshold, TOH_BLASTOFF, brg, {"units": "km"})
            logger.debug(f"departure from {rwy.name}, {brg:f}")

            p = addMovepoint(arr=self._premoves,
                             src=takeoff_hold,
                             alt=alt,
                             speed=0,
                             vspeed=0,
                             color=POSITION_COLOR.TAKE_OFF_HOLD.value,
                             mark=FLIGHT_PHASE.TAKE_OFF_HOLD.value,
                             ix=0)
            self.takeoff_hold = copy.deepcopy(p)  # we keep this special position for taxiing (end_of_taxi)
            logger.debug(f"takeoff hold at {rwy.name}, {TOH_BLASTOFF:f}")

            takeoff_distance = actype.getSI(ACPERF.takeoff_distance) * self.airport.runwayIsWet() / 1000  # must be km for destination()
            takeoff = destination(takeoff_hold, takeoff_distance, brg, {"units": "km"})

            p = addMovepoint(arr=self._premoves,
                             src=takeoff,
                             alt=alt,
                             speed=actype.getSI(ACPERF.takeoff_speed),
                             vspeed=actype.getSI(ACPERF.initial_climb_vspeed),
                             color=POSITION_COLOR.TAKE_OFF.value,
                             mark=FLIGHT_PHASE.TAKE_OFF.value,
                             ix=0)
            groundmv = takeoff_distance
            logger.debug(f"takeoff at {rwy.name}, {takeoff_distance:f}")

            self.addMessage(FlightMessage(subject=f"ACARS: {self.flight.aircraft.icao24} {FLIGHT_PHASE.TAKE_OFF.value} from {self.flight.departure.icao}",
                                          flight=self,
                                          sync=FLIGHT_PHASE.TAKE_OFF.value,
                                          info=self.getInfo()))
            is_grounded = False

            # initial climb, commonly accepted to above 1500ft AGL
            logger.debug("initialClimb")
            step = actype.initialClimb(alt)  # (t, d, altend)
            initial_climb_distance = step[1] / 1000  # km
            # find initial climb point

            # we climb on path to see if we reach indices...
            currpos, newidx = moveOn(fc, fcidx, p, initial_climb_distance)
            # we ignore currpos for now, we will climb straight, we ignore points
            # between fcidx and newidx during initial climb...
            initial_climb = destination(takeoff, initial_climb_distance, brg, {"units": "km"})
            currpos = addMovepoint(arr=self._premoves,
                                   src=initial_climb,
                                   alt=alt,
                                   speed=actype.getSI(ACPERF.initial_climb_speed),
                                   vspeed=actype.getSI(ACPERF.initial_climb_vspeed),
                                   color=POSITION_COLOR.INITIAL_CLIMB.value,
                                   mark="end_initial_climb",
                                   ix=newidx)
            logger.debug("initial climb end at %d, %f" % (newidx, initial_climb_distance))
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
            currpos = addMovepoint(arr=self._premoves,
                                   src=deptapt,
                                   alt=alt,
                                   speed=actype.getSI(ACPERF.takeoff_speed),
                                   vspeed=actype.getSI(ACPERF.initial_climb_vspeed),
                                   color=POSITION_COLOR.TAKE_OFF.value,
                                   mark=FLIGHT_PHASE.TAKE_OFF.value,
                                   ix=fcidx)
            logger.debug("origin added first point")

            self.addMessage(FlightMessage(subject=f"ACARS: {self.flight.aircraft.icao24} {FLIGHT_PHASE.TAKE_OFF.value} from {self.flight.departure.icao}",
                                          flight=self,
                                          sync=FLIGHT_PHASE.TAKE_OFF.value,
                                          info=self.getInfo()))
            is_grounded = False

            # initial climb, commonly accepted to above 1500ft AGL
            logger.debug("initialClimb")
            step = actype.initialClimb(alt)  # (t, d, altend)
            # find initial climb point
            groundmv = step[1]

            currpos, fcidx = moveOnLS(coll=self._premoves, reverse=False,
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

        # @todo: Transition to start of SID + follow SID
        # we have an issue if first point of SID is between TAKE_OFF and END_OF_INITIAL_CLIMB
        # but it is very unlikely (buy it may happen, in which case the solution is to remove the first point if SID)
        # Example of issue: BEY-DOH //DEP OLBA RW34 SID LEBO2F //ARR OTHH
        logger.debug("climbToFL100")
        step = actype.climbToFL100(currpos.altitude())  # (t, d, altend)
        groundmv = groundmv + step[1]
        currpos, fcidx = moveOnLS(coll=self._premoves, reverse=False,
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
            logger.debug("climbToFL150")
            step = actype.climbToFL240(currpos.altitude())  # (t, d, altend)
            groundmv = groundmv + step[1]
            currpos, fcidx = moveOnLS(coll=self._premoves, reverse=False,
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
                logger.debug("climbToFL240")
                step = actype.climbToFL240(currpos.altitude())  # (t, d, altend)
                groundmv = groundmv + step[1]
                currpos, fcidx = moveOnLS(coll=self._premoves, reverse=False,
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
                    logger.debug("climbToCruise")
                    step = actype.climbToCruise(currpos.altitude(), self.flight.getCruiseAltitude())  # (t, d, altend)
                    groundmv = groundmv + step[1]
                    currpos, fcidx = moveOnLS(coll=self._premoves, reverse=False,
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
                logger.debug("climbToCruise below FL240")
                step = actype.climbToCruise(currpos.altitude(), self.flight.getCruiseAltitude())  # (t, d, altend)
                groundmv = groundmv + step[1]
                currpos, fcidx = moveOnLS(coll=self._premoves, reverse=False,
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
                logger.warning(f"cruise speed below FL240: {cruise_speed:f} m/s")
        else:
            logger.debug("climbToCruise below FL150")
            step = actype.climbToCruise(currpos.altitude(), self.flight.getCruiseAltitude())  # (t, d, altend)
            groundmv = groundmv + step[1]
            currpos, fcidx = moveOnLS(coll=self._premoves, reverse=False,
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
            logger.warning(f"cruise speed below FL150: {cruise_speed:f} m/s")
            cruise_speed = (actype.getSI(ACPERF.climbFL150_speed) + actype.getSI(ACPERF.cruise_mach))/ 2

        # accelerate to cruise speed smoothly
        ACCELERATION_DISTANCE = 5000  # we reach cruise speed after 5km horizontal flight
        logger.debug("accelerate to cruise speed")
        currpos, fcidx = moveOnLS(coll=self._premoves, reverse=False,
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
        logger.debug("cruise at %d after %f" % (top_of_ascent_idx, groundmv))
        logger.debug(f"ascent added (+{len(self._premoves)} {len(self._premoves)})")
        # cruise until top of descent

        # PART 2: REVERSE: From brake on runway (end of roll out) to top of descent
        #
        #
        logger.debug(f"arrival to {self.flight.arrival.icao} " + "=" * 30)
        FINAL_ALT = 1000*FT     # Altitude ABG at which we start final
        APPROACH_ALT = 3000*FT  # Altitude ABG at which we perform approach path before final
        STAR_ALT = 6000*FT      # Altitude ABG at which we perform STAR path before approach
        LAND_TOUCH_DOWN = 0.4   # km, distance of touch down from the runway threshold (given in CIFP)

        # Alternative 1: VSPEED = 600ft/min for all aircrafts
        FINAL_VSPEED = 600

        if actype.getSI(ACPERF.landing_speed) is not None and actype.getSI(ACPERF.landing_speed) > 0:
            # Alternative 2 : VSPEED adjusted to have an angle/ratio of 3% (common)
            # Note: Landing speed is in kn. 1 kn = 101.26859 ft/min :-)
            FINAL_VSPEED = 0.03 * actype.get(ACPERF.landing_speed) * 101.26859  # in ft/min

        final_speed_ms = FINAL_VSPEED * FT / 60  # in meters/sec
        logger.debug(f"final vspeed {actype.typeId}: {round(final_speed_ms, 2)} m/s, {round(FINAL_VSPEED, 2)} ft/min")

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
            touch_down = destination(rwy_threshold, LAND_TOUCH_DOWN, brg, {"units": "km"})
            logger.debug(f"(rev) arrival runway {rwy.name}, {brg:f}")

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
            logger.debug(f"(rev) end roll out at {rwy.name}, {rollout_distance:f}, {alt:f}")
            self.end_rollout = copy.deepcopy(currpos)  # we keep this special position for taxiing (start_of_taxi)

            # Point just before is touch down
            p = addMovepoint(arr=revmoves,
                             src=touch_down,
                             alt=alt,
                             speed=actype.getSI(ACPERF.landing_speed),
                             vspeed=0,
                             color=POSITION_COLOR.TOUCH_DOWN.value,
                             mark=FLIGHT_PHASE.TOUCH_DOWN.value,
                             ix=len(fc)-fcidx)
            logger.debug(f"(rev) touch down at {rwy.name}, {LAND_TOUCH_DOWN:f}, {alt:f}")

            self.addMessage(FlightMessage(subject=f"ACARS: {self.flight.aircraft.icao24} {FLIGHT_PHASE.TOUCH_DOWN.value} at {self.flight.arrival.icao}",
                                          flight=self,
                                          sync=FLIGHT_PHASE.TOUCH_DOWN.value,
                                          info=self.getInfo()))
            is_grounded = False

            # we move to the final fix at max FINAL_ALT ft, landing speed, FINAL_VSPEED (ft/min), from touchdown
            logger.debug("(rev) final")
            step = actype.descentFinal(alt+FINAL_ALT, alt, final_speed_ms)  # (t, d, altend)
            final_distance = step[1] / 1000  # km
            # find initial climb point

            # we (reverse) descent on path to see if we reach indices...
            p, newidx = moveOn(fc, fcidx, p, final_distance)

            # we ignore currpos for now, we will descent straight, we ignore points
            # between fcidx and newidx during final descent...
            final_fix = destination(touch_down, final_distance, brg + 180, {"units": "km"})

            currpos = addMovepoint(arr=revmoves,
                                   src=final_fix,
                                   alt=alt+FINAL_ALT,
                                   speed=actype.getSI(ACPERF.landing_speed),
                                   vspeed=final_speed_ms,
                                   color=POSITION_COLOR.FINAL.value,
                                   mark=FLIGHT_PHASE.FINAL.value,
                                   ix=newidx)
            logger.debug("(rev) final at new=%d(old=%d), %f" % (newidx, fcidx, final_distance))
            groundmv = groundmv + final_distance
            # we ignore vertices between takeoff and initial_climb
            # we go in straight line and ignore self._premoves, skipping eventual points
            fcidx = newidx


            # XXXXXX
            groundmv = groundmv + step[1]
            # from approach alt to final fix alt
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
        else:
            arrvapt = fc[fcidx]
            alt = arrvapt.altitude()
            if alt is None:
                logger.warning(f"(rev) arrival airport has no altitude: {arrvapt}")
                alt = 0

            currpos = addMovepoint(arr=revmoves,
                                   src=arrvapt,
                                   alt=alt,
                                   speed=actype.getSI(ACPERF.landing_speed),
                                   vspeed=final_speed_ms,
                                   color=POSITION_COLOR.DESTINATION.value,
                                   mark="destination",
                                   ix=len(fc)-fcidx)
            logger.debug("(rev) destination added as last point")

            self.addMessage(FlightMessage(subject=f"ACARS: {self.flight.aircraft.icao24} {FLIGHT_PHASE.TOUCH_DOWN.value} at {self.flight.arrival.icao}",
                                          flight=self,
                                          sync=FLIGHT_PHASE.TOUCH_DOWN.value,
                                          info=self.getInfo()))
            is_grounded = False

            # we move to the final fix at max 3000ft, approach speed from airport last point, vspeed=FINAL_VSPEED
            logger.debug("(rev) final")
            step = actype.descentFinal(alt+FINAL_ALT, alt, final_speed_ms)  # (t, d, altend)
            groundmv = groundmv + step[1]
            # find final fix point
            currpos, fcidx = moveOnLS(coll=revmoves, reverse=True,
                                      fc=fc,
                                      fcidx=fcidx,
                                      currpos=currpos,
                                      dist=step[1],
                                      alt=alt+APPROACH_ALT,
                                      speed=actype.getSI(ACPERF.landing_speed),
                                      vspeed=final_speed_ms,
                                      color=POSITION_COLOR.FINAL.value,
                                      mark="start_of_final",
                                      mark_tr=FLIGHT_PHASE.FINAL.value)

        # if type(self).__name__ == "ArrivalMove":
        # find first point of approach:
        k = len(fc) - 1
        while fc[k].getProp(FEATPROP.PLAN_SEGMENT_TYPE.value) != "appch" and k > 0:
            k = k - 1
        if k == 0:
            logger.warning("no approach found")
        else:
            logger.debug("(rev) start of approach at index %d, %s" % (k, fc[k].getProp(FEATPROP.PLAN_SEGMENT_TYPE.value)))
            if k <= fcidx:
                logger.debug("(rev) final fix seems further away than start of apprach")
            else:
                logger.debug("(rev) flight level to final fix")
                # add all approach points between start to approach to final fix
                for i in range(fcidx+1, k):
                    wpt = fc[i]
                    # logger.debug("APPCH: flight level: %d %s" % (i, wpt.getProp(FEATPROP.PLAN_SEGMENT_TYPE.value)))
                    p = addMovepoint(arr=revmoves,
                                     src=wpt,
                                     alt=alt+APPROACH_ALT,
                                     speed=actype.getSI(ACPERF.approach_speed),
                                     vspeed=0,
                                     color=POSITION_COLOR.APPROACH.value,
                                     mark=FLIGHT_PHASE.APPROACH.value,
                                     ix=len(fc)-i)
                    # logger.debug("adding remarkable point: %d %s (%d)" % (i, p.getProp(FEATPROP.MARK), len(revmoves)))

                # add start of approach
                currpos = addMovepoint(arr=revmoves,
                                       src=fc[k],
                                       alt=alt+APPROACH_ALT,
                                       speed=actype.getSI(ACPERF.approach_speed),
                                       vspeed=0,
                                       color=POSITION_COLOR.APPROACH.value,
                                       mark="start_of_approach",
                                       ix=len(fc)-k)
                # logger.debug("adding remarkable point: %d %s (%d)" % (k, currpos.getProp(FEATPROP.MARK), len(revmoves)))

                fcidx = k

        # find first point of star:
        k = len(fc) - 1
        while fc[k].getProp(FEATPROP.PLAN_SEGMENT_TYPE.value) != "star" and k > 0:
            k = k - 1
        if k == 0:
            logger.warning("(rev) no star found")
        else:
            logger.debug("(rev) start of star at index %d, %s" % (k, fc[k].getProp(FEATPROP.PLAN_SEGMENT_TYPE.value)))
            if k <= fcidx:
                logger.debug("(rev) final fix seems further away than start of star")
            else:
                logger.debug("(rev) flight level to start of approach")
                # add all approach points between start to approach to final fix
                for i in range(fcidx+1, k):
                    wpt = fc[i]
                    # logger.debug("STAR: flight level: %d %s" % (i, wpt.getProp(FEATPROP.PLAN_SEGMENT_TYPE.value)))
                    p = addMovepoint(arr=revmoves,
                                     src=wpt,
                                     alt=alt+STAR_ALT,
                                     speed=actype.getSI(ACPERF.approach_speed),
                                     vspeed=0,
                                     color=POSITION_COLOR.APPROACH.value,
                                     mark="star",
                                     ix=len(fc)-i)

                    # logger.debug("adding remarkable point: %d %s (%d)" % (i, p.getProp(FEATPROP.MARK), len(revmoves)))
                # add start of approach
                currpos = addMovepoint(arr=revmoves,
                                       src=fc[k],
                                       alt=alt+STAR_ALT,
                                       speed=actype.getSI(ACPERF.approach_speed),
                                       vspeed=0,
                                       color=POSITION_COLOR.APPROACH.value,
                                       mark="start_of_star",
                                       ix=len(fc)-k)
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
                #         p.setProp(FEATPROP.MARK.value, FLIGHT_PHASE.HOLDING.value)
                #         p.setProp(FEATPROP.FLIGHT_PLAN_INDEX.value, i)
                #         p.setProp("holding-pattern-idx", holdidx)
                #         holdidx = holdidx - 1
                #         revmoves.append(p)
                #     logger.debug(".. done (%d points added)" % (len(hold_pts)))
                # else:
                #     logger.debug("holding fix %s not found" % (self.holdingpoint))

                fcidx = k

        if self.flight.flight_level > 100:
            # descent from FL100 to first approach point
            logger.debug("(rev) descent to star altitude")
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
                logger.debug("(rev) descent to FL100")
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
                    logger.debug("(rev) descent from cruise alt to FL240")
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
                logger.debug("(rev) descent from cruise alt under FL240 to FL100")
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
            logger.debug("(rev) descent from cruise alt under FL100 to approach alt")
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
        logger.debug("(rev) decelerate from cruise speed to first descent speed (which depends on alt...)")
        groundmv = groundmv + DECELERATION_DISTANCE
        currpos, fcidx = moveOnLS(coll=revmoves, reverse=True,
                                  fc=fc,
                                  fcidx=fcidx,
                                  currpos=currpos,
                                  dist=DECELERATION_DISTANCE,
                                  alt=self.flight.getCruiseAltitude(),
                                  speed=cruise_speed,
                                  vspeed=0,
                                  color=POSITION_COLOR.CRUISE.value,
                                  mark="end_of_cruise_speed",
                                  mark_tr=FLIGHT_PHASE.CRUISE.value)

        top_of_decent_idx = fcidx + 1 # we reach top of descent between idx and idx+1, so we cruise until idx+1
        logger.debug("(rev) reverse descent at %d after %f" % (top_of_decent_idx, groundmv))
        # we .reverse() array:
        top_of_decent_idx = len(self.flight.flightplan_wpts) - top_of_decent_idx  - 1
        logger.debug("(rev) cruise until %d, descent after %d, remains %f to destination" % (top_of_decent_idx, top_of_decent_idx, groundmv))

        # PART 3: Join top of ascent to top of descent at cruise speed
        #
        # We copy waypoints from start of cruise to end of cruise
        logger.debug("cruise")
        if top_of_decent_idx > top_of_ascent_idx:
            # logger.debug("adding cruise: %d -> %d" % (top_of_ascent_idx, top_of_decent_idx))
            for i in range(top_of_ascent_idx, top_of_decent_idx):
                wpt = self.flight.flightplan_wpts[i]
                # logger.debug("adding cruise: %d %s" % (i, wpt.getProp(FEATPROP.PLAN_SEGMENT_TYPE.value)))

                p = addMovepoint(arr=self._premoves,
                                 src=wpt,
                                 alt=self.flight.getCruiseAltitude(),
                                 speed=cruise_speed,
                                 vspeed=0,
                                 color=POSITION_COLOR.CRUISE.value,
                                 mark=FLIGHT_PHASE.CRUISE.value,
                                 ix=i)
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
            f.setProp(FEATPROP.PREMOVE_INDEX.value, idx)
            idx = idx + 1

        logger.debug(f"descent added (+{len(revmoves)} {len(self._premoves)})")
        # printFeatures(self._premoves, "holding")

        logger.debug("terminated " + "=" * 30)
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

        self.moves = []
        last_speed = 100  # @todo: should fetch another reasonable value from aircraft performance.
        # Add first point
        self.moves.append(self._premoves[0])

        for i in range(1, len(self._premoves) - 1):
            if not should_do_st(self._premoves, i):
                logger.debug("skipping %d (special mark)" % (i))
                self.moves.append(self._premoves[i])
            else:
                li = LineString([self._premoves[i-1]["geometry"]["coordinates"], self._premoves[i]["geometry"]["coordinates"]])
                lo = LineString([self._premoves[i]["geometry"]["coordinates"], self._premoves[i+1]["geometry"]["coordinates"]])
                s = last_speed  # arrin[i].speed()
                if s is None:
                    s = last_speed
                arc = standard_turn_flyby(li, lo, turnRadius(s))
                last_speed = s

                if arc is not None:
                    mid = arc[int(len(arc) / 2)]
                    mid["properties"] = self._premoves[i]["properties"]
                    for p in arc:
                        self.moves.append(MovePoint(geometry=p["geometry"], properties=mid["properties"]))
                else:
                    self.moves.append(self._premoves[i])

        # Add last point too
        self.moves.append(self._premoves[-1])

        # Sets unique index on flight movement features
        idx = 0
        for f in self.moves:
            f.setProp(FEATPROP.MOVE_INDEX.value, idx)
            idx = idx + 1

        logger.debug(f"completed {len(self._premoves)}, {len(self.moves)} with standard turns")
        return (True, "Movement::standard_turns added")


    def interpolate(self):
        """
        Compute interpolated values for altitude and speed based on distance.
        This is a simple linear interpolation based on distance between points.
        Runs for flight portion of flight.
        """
        to_interp = self.moves
        # before = []
        check = "altitude"
        logger.debug("interpolating ..")
        for name in ["speed", "vspeed", "altitude"]:
            logger.debug(f".. {name} ..")
            if name == check:
                before = list(map(lambda x: x.getProp(name), to_interp))
            status = doInterpolation(to_interp, name)
            if not status[0]:
                logger.warning(status[1])
        logger.debug(".. done.")

        logger.debug("checking and transposing altitudes to geojson coordinates..")
        for f in to_interp:
            if len(f["geometry"]["coordinates"]) == 2:
                a = f.altitude()
                if a is not None:
                    f["geometry"]["coordinates"].append(float(a))
                else:
                    logger.warning(f"no altitude? {f['property'][name] if name in f['property'] else '?'}")
        logger.debug(".. done.")

        # name = check
        # for i in range(len(to_interp)):
        #     v = to_interp[i].getProp(name) if to_interp[i].getProp(name) is not None and to_interp[i].getProp(name) != "None" else "none"
        #     logger.debug("%d: %s -> %s." % (i, before[i] if before[i] is not None else -1, v))


        # logger.debug("last point %d: %f, %f" % (len(self.moves), self.moves[-1].speed(), self.moves[-1].altitude()))
        # i = 0
        # for f in self._premoves:
        #     s = f.speed()
        #     a = f.altitude()
        #     logger.debug("alter: %d: %f %f" % (i, s if s is not None else -1, a if a is not None else -1))
        #     i = i + 1

        return (True, "Movement::interpolated speed and altitude")


    def time(self):
        """
        Time 0 is start of roll for takeoff (Departure) or takeoff from origin airport (Arrival).
        Last time is touch down at destination (Departure) or end of roll out (Arrival).
        """
        if self.moves is None:
            return (False, "Movement::time no move")

        status = doTime(self.moves)
        if not status[0]:
            logger.warning(status[1])
            return status

        for f in self.moves:
            f.setProp(FEATPROP.SAVED_TIME.value, f.time())

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

        logger.debug("interpolate speed ..")
        status = doInterpolation(self.taxipos, "speed")
        if not status[0]:
            logger.warning(status[1])
            return status

        logger.debug(".. compute time ..")
        status = doTime(self.taxipos)
        if not status[0]:
            logger.warning(status[1])
            return status

        for f in self.taxipos:
            f.setProp(FEATPROP.SAVED_TIME.value, f.time())
            f.setProp(FEATPROP.GROUNDED.value, True)

        logger.debug(".. done.")

        return (True, "Movement::taxiInterpolateAndTime done")


    def add_tmo(self, TMO: float = 10 * NAUTICAL_MILE):
        # We add a TMO point (Ten (nautical) Miles Out). Should be set before we interpolate.
        # TMO = 10 * NAUTICAL_MILE  # km
        idx = len(self.moves) - 1  # last is end of roll, before last is touch down.
        totald = 0
        prev = 0
        while totald < TMO and idx > 1:
            idx = idx - 1
            d = distance(self.moves[idx], self.moves[idx - 1])
            prev = totald
            totald = totald + d
            # logger.debug("add_tmo: %d: d=%f, t=%f" % (idx, d, totald))
        # idx points at
        left = TMO - prev
        # logger.debug("add_tmo: %d: left=%f, TMO=%f" % (idx, left, TMO))
        brng = bearing(self.moves[idx], self.moves[idx - 1])
        tmopt = destination(self.moves[idx], left, brng, {"units": "km"})

        tmomp = MovePoint(geometry=tmopt["geometry"], properties={})
        tmomp.setProp(FEATPROP.MARK.value, FLIGHT_PHASE.TEN_MILE_OUT.value)

        d = distance(tmomp, self.moves[-2])  # last is end of roll, before last is touch down.

        self.moves.insert(idx, tmomp)
        logger.debug(f"added at ~{d:f} km, ~{d / NAUTICAL_MILE:f} nm from touch down")

        self.addMessage(FlightMessage(subject=f"{self.flight_id} {FLIGHT_PHASE.TEN_MILE_OUT.value}",
                                      flight=self,
                                      sync=FLIGHT_PHASE.TEN_MILE_OUT.value))

        return (True, "Movement::add_tmo added")


    def add_faraway(self, FARAWAY: float = 100 * NAUTICAL_MILE):
        # We add a FARAWAY point when flight is at FARAWAY from begin of roll (i.e. at FARAWAY from airport).
        start = self.moves[0]
        idx = 0
        totald = 0
        prev = 0
        while totald < FARAWAY and idx < (len(self.moves) - 1):
            totald = distance(start, self.moves[idx + 1])
            prev = totald
            idx = idx + 1
            # logger.debug("add_faraway: %d: d=%f, t=%f" % (idx, d, totald))
        # idx points at
        left = FARAWAY - prev
        # logger.debug("add_faraway: %d: left=%f, FARAWAY=%f" % (idx, left, FARAWAY))
        if idx < len(self.moves) - 1:
            brng = bearing(self.moves[idx], self.moves[idx + 1])
            tmopt = destination(self.moves[idx], left, brng, {"units": "km"})

            tmomp = MovePoint(geometry=tmopt["geometry"], properties={})
            tmomp.setProp(FEATPROP.MARK.value, FLIGHT_PHASE.FAR_AWAY.value)

            d = distance(start, tmomp)
            self.moves.insert(idx, tmomp)
            logger.debug(f"added at ~{d:f} km, ~{d / NAUTICAL_MILE:f} nm from airport")

            self.addMessage(FlightMessage(subject=f"{self.flight_id} {FLIGHT_PHASE.FAR_AWAY.value}",
                                          flight=self,
                                          sync=FLIGHT_PHASE.FAR_AWAY.value))
        else:
            logger.debug(f"less than {FARAWAY} miles, no FAR_AWAY point added")

        return (True, "Movement::add_faraway added")


class TowMovement(Movement):
    """
    Movement build the detailed path of the aircraft, both on the ground (taxi) and in the air,
    from takeoff to landing and roll out.
    """
    def __init__(self, flight: Flight, newramp: "Ramp", airport: ManagedAirportBase):
        Movement.__init__(self, airport=airport)
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
        parkingpos.setProp(FEATPROP.MARK.value, FLIGHT_PHASE.OFFBLOCK.value)
        fc.append(parkingpos)
        if show_pos:
            logger.debug(f"tow start: {parkingpos}")

        self.addMessage(FlightMessage(subject=f"ACARS: {self.flight.aircraft.icao24} {FLIGHT_PHASE.OFFBLOCK.value} from {self.flight.ramp.getName()}",
                                      flight=self,
                                      sync=FLIGHT_PHASE.OFFBLOCK.value))

        # we call the move from packing position to taxiway network the "pushback"
        pushback_end = self.airport.taxiways.nearest_point_on_edge(parking)
        if show_pos:
            logger.debug(f"pushback_end: {pushback_end[0]}")
        if pushback_end[0] is None:
            logger.warning("could not find pushback end")

        pushbackpos = MovePoint.new(pushback_end[0])
        pushbackpos.setSpeed(SLOW_SPEED)
        pushbackpos.setColor("#880088")  # parking
        pushbackpos.setProp(FEATPROP.MARK.value, "pushback")
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
                towpos.setProp(FEATPROP.MARK.value, "tow")
                towpos.setProp("_taxiways", vtx.id)
                fc.append(towpos)
            fc[-1].setProp(FEATPROP.MARK.value, "tow end vertex")
        else:
            logger.warning("no tow route found")

        newparkingentrypos = MovePoint.new(newparking_entry[0])
        newparkingentrypos.setSpeed(SLOW_SPEED)
        newparkingentrypos.setColor("#880088")  # parking entry, is on taxiway network
        newparkingentrypos.setProp(FEATPROP.MARK.value, "tow end")
        fc.append(newparkingentrypos)

        # This is the last point, we make sure available info is in props
        newparkingpos = MovePoint.new(parking)
        newparkingpos.setSpeed(0)
        newparkingpos.setVSpeed(0)
        newparkingpos.setAltitude(self.airport.altitude())
        newparkingpos.setColor("#880088")  # parking
        newparkingpos.setProp(FEATPROP.MARK.value, FLIGHT_PHASE.ONBLOCK.value)
        fc.append(newparkingpos)

        if show_pos:
            logger.debug(f"end: {newparking}")
        else:
            logger.debug(f"end: parking {newparking.getProp('name')}")

        for f in fc:
            f.setProp(FEATPROP.GROUNDED.value, True)

        tow = {
            "from": self.flight.ramp,
            "to": self.newramp,
            "move": fc
        }
        self.tows.append(tow)  ## self.tows is array of tows since there might be many tows.
        self.flight.ramp = self.newramp
        logger.info(f"FlightMovement::tow completed: flight {self.flight_id}: from {tow['from'].getId()} to {tow['to'].getId()}"
                  + f" at @todo minutes {'after onblock' if self.is_arrival else 'before offblock'}")

        logger.debug(f"{len(fc)} moves")

        return (True, "FlightMovement::tow completed")


class ArrivalMove(FlightMovement):
    """
    Movement for an arrival flight
    """
    def __init__(self, flight: Flight, airport: ManagedAirportBase):
        FlightMovement.__init__(self, flight=flight, airport=airport)


    def getMoves(self):
        prev = super().getMoves()
        if len(prev) == 0:
            return prev   # len(prev) == 0
        start = prev[-1].time()  # take time of last event of flight
        for f in self.taxipos:
            f.setTime(start + f.getProp(FEATPROP.SAVED_TIME.value))
        return prev + self.taxipos


    def taxi(self):
        """
        Compute taxi path for arrival, from roll out position, to runway exit to parking.
        """
        show_pos = False
        fc = []

        endrolloutpos = MovePoint.new(self.end_rollout)
        endrolloutpos.setSpeed(TAXI_SPEED)
        endrolloutpos.setColor("#880088")  # parking
        endrolloutpos.setProp(FEATPROP.MARK.value, "end rollout")
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
        taxistartpos.setProp(FEATPROP.MARK.value, "taxi start")
        fc.append(taxistartpos)

        taxistart_vtx = self.airport.taxiways.nearest_vertex(taxi_start[0])
        if show_pos:
            logger.debug(f"taxi in: taxi start vtx: {taxistart_vtx}")
        if taxistart_vtx[0] is None:
            logger.warning("taxi in: could not find taxi start vertex")
        taxistartpos = MovePoint.new(taxistart_vtx[0])
        taxistartpos.setSpeed(TAXI_SPEED)
        taxistartpos.setColor("#880088")  # parking
        taxistartpos.setProp(FEATPROP.MARK.value, "taxi start vertex")
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
                taxipos.setProp(FEATPROP.MARK.value, "taxi")
                taxipos.setProp("_taxiways", vtx.id)
                fc.append(taxipos)
            fc[-1].setProp(FEATPROP.MARK.value, "taxi end vertex")
        else:
            logger.warning("taxi in: no taxi route found")

        parkingentrypos = MovePoint.new(parking_entry[0])
        parkingentrypos.setSpeed(SLOW_SPEED)
        parkingentrypos.setColor("#880088")  # parking entry, is on taxiway network
        parkingentrypos.setProp(FEATPROP.MARK.value, "taxi end")
        fc.append(parkingentrypos)

        # This is the last point, we make sure available info is in props
        parkingpos = MovePoint.new(parking)
        parkingpos.setSpeed(0)
        parkingpos.setVSpeed(0)
        parkingpos.setAltitude(self.airport.altitude())
        parkingpos.setColor("#880088")  # parking
        parkingpos.setProp(FEATPROP.MARK.value, FLIGHT_PHASE.ONBLOCK.value)
        fc.append(parkingpos)

        self.addMessage(FlightMessage(subject=f"ACARS: {self.flight.aircraft.icao24} {FLIGHT_PHASE.ONBLOCK.value} at {self.flight.ramp.getName()}",
                                      flight=self,
                                      sync=FLIGHT_PHASE.ONBLOCK.value))

        if show_pos:
            logger.debug(f"taxi in: taxi end: {parking}")
        else:
            logger.debug(f"taxi in: taxi end: parking {parking.getProp('name')}")

        self.taxipos = fc
        logger.debug(f"taxi in: taxi {len(self.taxipos)} moves")

        return (True, "ArrivalMove::taxi completed")


class DepartureMove(FlightMovement):
    """
    Movement for an departure flight
    """
    def __init__(self, flight: Flight, airport: ManagedAirportBase):
        FlightMovement.__init__(self, flight=flight, airport=airport)


    def getMoves(self):
        prev = self.taxipos
        if len(prev) == 0:
            return prev   # len(prev) == 0
        start = prev[-1].time()  # time of flight starts at end of taxi
        nextmv = super().getMoves()
        for f in nextmv:
            f.setTime(start + f.getProp(FEATPROP.SAVED_TIME.value))
        return self.taxipos + nextmv


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
        parkingpos.setProp(FEATPROP.MARK.value, FLIGHT_PHASE.OFFBLOCK.value)
        fc.append(parkingpos)

        self.addMessage(FlightMessage(subject=f"ACARS: {self.flight.aircraft.icao24} {FLIGHT_PHASE.OFFBLOCK.value} from {self.flight.ramp.getName()}",
                                      flight=self,
                                      sync=FLIGHT_PHASE.OFFBLOCK.value))

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
        pushbackpos.setProp(FEATPROP.MARK.value, "pushback")
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
                        taxipos.setProp(FEATPROP.MARK.value, "taxi")
                        taxipos.setProp("_taxiways", vtx.id)
                        fc.append(taxipos)
                    fc[-1].setProp(FEATPROP.MARK.value, "taxi-hold")
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
                taxipos.setProp(FEATPROP.MARK.value, "taxi")
                taxipos.setProp("_taxiways", vtx.id)
                fc.append(taxipos)
            fc[-1].setProp(FEATPROP.MARK.value, "runway hold")
        else:
            logger.warning("taxi out: no taxi route found to runway hold")

        taxiendpos = MovePoint.new(taxi_end[0])
        taxiendpos.setSpeed(TAXI_SPEED)
        taxiendpos.setColor("#880088")  # parking
        taxiendpos.setProp(FEATPROP.MARK.value, "taxi end")
        fc.append(taxiendpos)

        takeoffholdpos = MovePoint.new(self.takeoff_hold)
        takeoffholdpos.setSpeed(0)
        takeoffholdpos.setColor("#880088")  # parking
        takeoffholdpos.setProp(FEATPROP.MARK.value, "takeoff hold")
        fc.append(takeoffholdpos)

        if show_pos:
            logger.debug(f"taxi out: taxi end: {takeoffholdpos}")
        else:
            rwy_name = self.flight.rwy.name if self.flight.rwy is not None else "no runway"
            logger.debug(f"taxi out: taxi end: holding for runway {rwy_name}")

        self.taxipos = fc
        logger.debug(f"taxi out: taxi {len(self.taxipos)} moves")

        return (True, "DepartureMove::taxi completed")
