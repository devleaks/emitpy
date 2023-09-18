"""
Emit instance is a list of EmitPoints to broadcast along the Movement path.
The instance is partially passivated in a cache and can be recovered with sufficient
information.
"""
import os
import io
import json
import logging

from datetime import datetime, timedelta, timezone

from geojson import FeatureCollection
from geojson.geometry import Geometry
from turfpy.measurement import distance, bearing, destination

from tabulate import tabulate

from redis.commands.json.path import Path

import emitpy
from emitpy.geo import MovePoint, cleanFeatures, findFeatures, Movement, toTraffic, toLST
from emitpy.utils import interpolate as doInterpolation, compute_headings, key_path

from emitpy.constants import SLOW_SPEED, FEATPROP, FLIGHT_PHASE, SERVICE_PHASE, MISSION_PHASE
from emitpy.constants import REDIS_DATABASE, REDIS_TYPE, REDIS_DATABASES
from emitpy.constants import RATE_LIMIT, EMIT_RANGE, MOVE_TYPE, EMIT_TYPE
from emitpy.constants import DEFAULT_FREQUENCY
from emitpy.parameters import MANAGED_AIRPORT_AODB

logger = logging.getLogger("Emit")


BROADCAST_AT_VERTEX = False  # Tells whether emit should be produced at movement vertices (waypoints, cross roads, etc.)
# Reality is False, but for debugging purposes setting to True can help follow paths/linestrings.


class EmitPoint(MovePoint):
    """
    An EmitPoint is a Feature<Point> with additional information for emission.
    All information to be emited in included into the EmitPoint.
    """
    def __init__(self, geometry: Geometry, properties: dict):
        MovePoint.__init__(self, geometry=geometry, properties=properties)


class Emit(Movement):
    """
    Emit takes an array of MovePoints to produce a FeatureCollection of decorated features ready for emission.
    """
    def __init__(self, move: Movement):
        Movement.__init__(self, airport=move.airport, reason=move)
        self.move = move

        self.emit_id = None
        self.emit_type = None
        self.emit_meta = None
        self.format = None
        self.frequency = None  # seconds
        self._emit_points = []  # [ EmitPoint ], time-relative emission of messages
        self._scheduled_points = []  # [ EmitPoint ], a copy of self._emit_points but with actual emission time (absolute time)
        self.move_points = []
        self.props = {}  # general purpose properties added to each emit point

        self.curr_starttime = None
        self.curr_schedule = None
        self.curr_syncmark = None

        if type(self).__name__ == "Emit" and move is None:
            logger.error("move cannot be None for new Emit")

        if move is not None:
            # We initiate an emit from a movement
            self.emit_id = self.move.getId()
            m = self.move.getInfo()
            self.emit_type = m.get("type", REDIS_DATABASE.UNKNOWN.value)
            self.move_points = self.move.getMovePoints()  # this takes a COPY
            self.props = self.move.getInfo()  # collect common props from movement
            self.props["emit"] = self.getInfo() # add meta data about this emission
            logger.debug(f"{len(self.move_points)} move points to emit with {len(self.props)} properties")


    @staticmethod
    def getCombo():
        a = []
        for f in FLIGHT_PHASE:
            n = f.value[0].upper() + f.value[1:] + " (flight)"
            a.append((f.value, n))
        for f in SERVICE_PHASE:
            n = f.value[0].upper() + f.value[1:] + " (service)"
            a.append((f.value, n))
        return a


    def getId(self):
        """
        Gets the underlying movement identifier. The movement identifier contains the type of movement
        (flight, service, or mission)
        """
        return self.emit_id


    def getInfo(self):
        """
        Emit's own identifier based on the underlying movement identifier.
        """
        ty = REDIS_DATABASE.UNKNOWN.value
        if self.move is not None:
            m = self.move.getInfo()
            if m is not None and "type" in m:
                ty = m["type"]
        if self.emit_type is None and ty != REDIS_DATABASE.UNKNOWN.value:
            self.emit_type = ty
        return {
            FEATPROP.VERSION.value: emitpy.__version__,
            "type": "emit",
            "emit-type": self.emit_type if self.emit_type is not None else ty,
            "ident": self.emit_id,
            "frequency": self.frequency,
            "time-bracket": self.getTimeBracket(as_string=True),
            "version": self.version
        }


    def getEmitPoints(self):
        return self._emit_points

    def getPoints(self):
        return self._emit_points

    def setEmitPoints(self, emit_points):
        self._emit_points = emit_points

    def has_emit_points(self):
        return self._emit_points is not None and len(self.getEmitPoints()) > 0

    def getSource(self):
        if self.move is not None:
            return self.move.getSource()
        logger.error("no movement")
        return None


    def getMessages(self):
        m = super().getMessages()  # this emit's messages
        # logger.debug(f"added super()")
        if self.move is not None:
            m = m + self.move.getMessages()
            # logger.debug(f"added source")
        return m


    def getMeta(self):
        """
        Emit identifier augmented with data from the movement.
        """
        # logger.debug(f"from Emit")
        self.emit_meta = self.getInfo()
        self.emit_meta["props"] = self.props
        self.emit_meta["marks"] = self.getTimedMarkList()
        if self.move is not None:
            self.emit_meta["move"] = self.move.getInfo()
        source = self.getSource()
        if source is not None:
            self.emit_meta["time"] = source.getScheduleHistory(as_string=True)
        # logger.debug(f"{self.emit_meta}")
        return self.emit_meta


    def getKey(self, extension: str):
        db = REDIS_DATABASE.UNKNOWN.value
        if self.emit_type in REDIS_DATABASES.keys():
            db = REDIS_DATABASES[self.emit_type]
        else:
            logger.warning(f"invalid type {self.emit_type}, database unknown")
        if extension in [REDIS_TYPE.EMIT_META.value, REDIS_TYPE.EMIT_MESSAGE.value]:  # do not add frequency
            return key_path(db, self.emit_id, extension)
        frequency = self.frequency if self.frequency is not None else DEFAULT_FREQUENCY
        if extension is None:
            return key_path(db, self.emit_id, f"{frequency}")
        return key_path(db, self.emit_id, f"{frequency}", extension)


    def loadMeta(self, redis):
        meta_id = self.getKey(REDIS_TYPE.EMIT_META.value)
        if redis.exists(meta_id):
            self.emit_meta = json.loads(redis.get(meta_id))
            logger.debug(f"..got {len(self.props)} props")
        else:
            logger.debug(f"..no meta for {self.emit_type}")
        return (True, "Emit::loadMeta loaded")


    def saveMeta(self, redis):
        meta_id = self.getKey(REDIS_TYPE.EMIT_META.value)
        redis.delete(meta_id)
        redis.json().set(meta_id, Path.root_path(), self.getMeta())
        logger.debug(f".. meta saved {meta_id}")
        return (True, "Emit::saveMeta saved")


    def save(self, redis):
        """
        Save flight paths to file for emitted positions.
        """
        if redis is None:
            # return self.saveFile()
            return (True, "Emit::save: no Redis")

        if not self.has_emit_points():
            logger.warning("no emission point")
            return (False, "Emit::save: no emission point")

        emit_id = self.getKey(REDIS_TYPE.EMIT.value)

        # 1. Save emission points
        emit = {}
        for f in self.getEmitPoints():
            emit[json.dumps(f)] = f.getProp(FEATPROP.EMIT_REL_TIME.value)
        redis.delete(emit_id)
        redis.zadd(emit_id, emit)
        move_id = self.getKey("")

        # 2. Save KML (for flights only)
        # if callable(getattr(self.move, "getKML", None)):
        #     kml_id = self.getKey(REDIS_TYPE.EMIT_KML.value)
        #     redis.set(kml_id, self.move.getKML())
        #     logger.debug(f"saved kml")

        # 3. Save messages for broadcast
        mid = self.getKey(REDIS_TYPE.EMIT_MESSAGE.value)
        redis.delete(mid)
        for m in self.getMessages():
            redis.sadd(mid, json.dumps(m.getInfo()))
        logger.debug(f"saved {redis.scard(mid)} messages")

        logger.debug(f"saved {move_id}")
        return self.saveMeta(redis)


    def write_debug(self, reason: str = ""):
        logger.warning("writing debug files..")
        basedir = os.path.join(MANAGED_AIRPORT_AODB, "debug")
        if not os.path.exists(basedir):
            os.mkdir(basedir)
            logger.info(f"directory {basedir} does not exist. created.")

        # Try to save situation...
        ident = self.getId()
        fnbase = os.path.join(basedir, f"debug-{reason}-{ident}-{datetime.now().isoformat()}-")
        self.move.saveFile()
        with open(fnbase + "meta.out", "w") as fp:
            json.dump(self.getMeta(), fp, indent=4)
        with open(fnbase + "debug-emit-info.out", "w") as fp:
            json.dump(self.getInfo(), fp, indent=4)
        with open(fnbase + "debug-emit-data.geojson", "w") as fp:
            json.dump(FeatureCollection(features=cleanFeatures(self.getEmitPoints())), fp, indent=4)
        with open(fnbase + "debug-move-info.out", "w") as fp:
            json.dump(self.move.getInfo(), fp, indent=4)
        # with open(fnbase + "debug-move-emit-data.geojson", "w") as fp:
        #     json.dump(FeatureCollection(features=cleanFeatures(self.getEmitPoints())), fp, indent=4)
        with open(fnbase + "debug-move-move-data.geojson", "w") as fp:
            json.dump(FeatureCollection(features=cleanFeatures(self.move.getMovePoints())), fp, indent=4)
        logger.warning(f"..written debug files {fnbase}")


    def saveFile(self):
        """
        Save flight paths to file for emitted positions.
        """
        if self.is_event_service():
            return (True, "Emit::saveFile: no need to save event service")

        # 1. Save "raw emits"
        # filename = os.path.join(basename + "-5-emit.json")
        # with open(filename, "w") as fp:
        #     json.dump(self.getEmitPoints(), fp, indent=4)

        # 2. Save "raw emits" and linestring
        # ls = Feature(geometry=asLineString(self.getEmitPoints()))
        # filename = os.path.join(basename + "-5-emit_ls.geojson")
        # with open(filename, "w") as fp:
        #     json.dump(FeatureCollection(features=cleanFeatures(self.getEmitPoints())+ [ls]), fp, indent=4)

        # 3. Save linestring with timestamp
        # Save for traffic analysis
        # logger.debug(f"{self.getInfo()}")

        ret = self.saveTraffic()
        if not ret[0]:
            logger.warning("could not save traffic file")

        ret = self.saveLST()
        if not ret[0]:
            logger.warning("could not save LST file")

        logger.debug(f"saved {self.getId()} files")
        return (True, "Emit::saveFile saved")


    def saveTraffic(self):
        """
        Save GSE paths to file for emitted positions for python traffic analysis
        """
        if self._scheduled_points is None or len(self._scheduled_points) == 0:
            logger.warning("no scheduled emission point")
            self.write_debug("saveTraffic")
            return (False, "Emit::saveTraffic: no scheduled emission point")

        logger.debug(f"emit has {len(self._scheduled_points)} positions, saving..")

        ident = self.getId()
        db = REDIS_DATABASES[self.emit_type] if self.emit_type in REDIS_DATABASES.keys() else REDIS_DATABASE.UNKNOWN.value
        basedir = os.path.join(MANAGED_AIRPORT_AODB, db)
        if not os.path.exists(basedir):
            os.mkdir(basedir)
            logger.info(f"directory {basedir} did not exist. created.")

        ls = toTraffic(self._scheduled_points)
        basename = os.path.join(basedir, ident)
        filename = os.path.join(basename + "-traffic.csv")
        with open(filename, "w") as fp:
            fp.write(ls)
        logger.debug(f"..saved {ident} for traffic analysis")

        return (True, "Emit::saveTraffic saved")


    def saveLST(self):
        """Saves emission for X-Plane Living Scenery Technology.

        Works for ground support vehicle (both missions and services).
        Need to have (virtual) path to 3D model for representation,
        otherwise default to marshall car.
        """
        if self.emit_type not in [EMIT_TYPE.SERVICE.value, EMIT_TYPE.MISSION.value]:
            logger.debug(f"no LST save for emit of type {self.emit_type}")
            return (True, "Emit::saveLST no necessary to save")

        if self._scheduled_points is None or len(self._scheduled_points) == 0:
            logger.warning("no scheduled emission point")
            self.write_debug("saveLST")
            return (False, "Emit::saveLST: no scheduled emission point")

        ident = self.getId()
        db = REDIS_DATABASES[self.emit_type] if self.emit_type in REDIS_DATABASES.keys() else REDIS_DATABASE.UNKNOWN.value
        basedir = os.path.join(MANAGED_AIRPORT_AODB, db)
        if not os.path.exists(basedir):
            os.mkdir(basedir)
            logger.info(f"directory {basedir} did not exist. created.")

        flight_id = ""
        if self.emit_type == EMIT_TYPE.SERVICE.value:
            flight = self.move.service.flight
            if flight is not None:
                flight_id = flight.getId()
            flight_dir = os.path.join(basedir, flight_id)
            if not os.path.exists(flight_dir):
                os.mkdir(flight_dir)
                logger.info(f"directory {flight_dir} did not exist. created.")

        # logger.debug(f"{self.getInfo()}")
        logger.debug(f"move has {len(self.move_points)} positions; saving..")
        lst = toLST(self)  # need to pass emit since move is not scheduled
        basename = os.path.join(basedir, flight_id, ident)
        filename = os.path.join(basename + ".lst")
        with open(filename, "w") as fp:
            fp.write(lst)
        logger.debug(f"..saved {ident} for Living Scenery Technology")

        return (True, "Emit::saveLST saved")


    def emit(self, frequency: int):
        # Utility subfunctions
        must_spit_out = False
        emit_details = False

        def has_already_mark(mark: str) -> bool:
            for e in self.getEmitPoints():
                if e.getMark() == mark:
                    return True
            return False

        def point_on_line(c, n, d):
            # brng = bearing(c, n)
            # dest = destination(c, d / 1000, brng, {"units": "km"})
            # if emit_details:
            #     logger.debug(f"d={d})")
            return MovePoint.convert(destination(c, d / 1000, bearing(c, n), {"units": "km"}))

        def time_distance_to_next_vtx(c0, idx):  # time it takes to go from c0 to vtx[idx+1]
            totald = distance(self.move_points[idx], self.move_points[idx+1])  * 1000  # km
            if totald == 0:  # same point...
                # logger.debug(f"same point i={idx}? Did not move?")
                return 0
            partiald = distance(self.move_points[idx], c0) * 1000  # km
            if partiald > totald:  # yes, it happens...
                logger.warning("partiald > totald? forcing partiald = totald")
                return 0

            portion = partiald / totald
            leftd = totald - partiald  # = distance(c0, self.move_points[idx+1])
            v0 = self.move_points[idx].speed()
            v1 = self.move_points[idx+1].speed()
            v = v0 + portion * (v1 - v0)
            # logger.debug(f"{round(leftd, 3)}, verif={round(distance(c0, self.move_points[idx+1])*1000, 3)}")
            v = max(v, SLOW_SPEED)
            t = 0
            if (v + v1) != 0:
                t = 2 * leftd / (v + v1)
            else:
                logger.warning("time_distance_to_next_vtx: v + v1 = 0?")
            # logger.debug(f"{idx}, tot={totald}, left={leftd}, t={t})")
            # logger.debug(f"done={partiald} ({portion}), v={v}, v0={v0}, v1={v1})")
            return t

        def destinationOnTrack(c0, duration, idx):  # from c0, moves duration seconds on edges at speed specified at vertices
            totald = distance(self.move_points[idx], self.move_points[idx+1]) * 1000  # km
            if totald == 0:  # same point...
                logger.warning(f"destinationOnTrack: same point i={idx}?")
                return None
            partiald = distance(self.move_points[idx], c0) * 1000  # km
            portion = partiald / totald
            v0 = self.move_points[idx].speed()
            v1 = self.move_points[idx+1].speed()
            v = v0 + portion * (v1 - v0)
            v = max(v, SLOW_SPEED)

            acc = (v1 * v1 - v0 * v0) / (2 * totald)  # a=(u²-v²)/2d
            hourrate = duration  # / 3600
            dist = v * hourrate + acc * hourrate * hourrate / 2

            # nextpos = point_on_line(currpos, self.move_points[idx+1], dist)
            # controld = distance(currpos, nextpos) * 1000  # km
            # logger.debug("(%d, v=%f, dur=%f, dist=%f, seglen=%f)" % (idx, v, duration, controld, totald))
            # return nextpos
            return point_on_line(currpos, self.move_points[idx+1], dist)

        def emit_point(idx, pos, time, reason, waypt=False):
            nonlocal must_spit_out
            e = EmitPoint.new(pos)
            e.setProp(FEATPROP.EMIT_REL_TIME.value, time)
            e.setProp(FEATPROP.EMIT_INDEX.value, len(self.getEmitPoints()))  # Sets unique index on emit features
            e.setProp(FEATPROP.BROADCAST.value, not waypt)
            if self.emit_type == "service" and e.getMark() is not None: # and e.getMark() is not None:
                logger.debug(f"added mark={e.getMark()}, reason={reason}, emit={e.getProp(FEATPROP.BROADCAST.value)}")

            # if GSE_EMIT_WHEN_STOPPED:
            #     e.setProp(FEATPROP.BROADCAST.value, not waypt)
            # else:
            #     e.setProp(FEATPROP.BROADCAST.value, not waypt and e.speed(0) > 0)
            if not e.hasColor():
                if waypt:
                    e.setColor("#eeeeee")
                    # logger.debug(f"emit_point:waypoint: {reason} i={idx} t={time} ({timedelta(seconds=time)}) s={e.speed()}")
                else:
                    e.setColor("#ccccff")
                    # logger.debug(f"emit_point: {reason} i={idx} t={time} ({timedelta(seconds=time)}) s={e.speed()}")
            self._emit_points.append(e)
            if e.getMark() is not None:
                must_spit_out = False
                if emit_details:
                    logger.debug(f"split out {e.getMark()}")
            # logger.debug(f"emit_point: dist2nvtx={round(distance(e, self.move_points[idx+1])*1000,1)} i={idx} e={len(self.getEmitPoints())}")

        def pause_at_vertex(curr_time, time_to_next_emit, pause: float, idx, pos, time, reason):
            nonlocal must_spit_out
            debug_pause = False
            if emit_details:
                logger.debug(f"pause i={idx} p={pause}, e={len(self.getEmitPoints())}")
            if pause < self.frequency:  # may be emit before reaching next vertex:
                if pause > time_to_next_emit:  # neet to emit before we reach next vertex
                    emit_time = curr_time + time_to_next_emit
                    emit_point(idx, pos, emit_time, reason, False) # waypt=False to emit
                    end_time = curr_time + pause
                    time_left = self.frequency - (pause - time_to_next_emit)
                    if emit_details:
                        logger.debug(f"pause before next emit: emit at vertex i={idx} p={pause}, e={len(self.getEmitPoints())}")
                    return (end_time, time_left)
                else:  # pause a little but not enough to emit
                    end_time = curr_time + pause
                    time_left = time_to_next_emit - pause
                    if emit_details:
                        logger.debug(f"pause a little but do not emit at vertex: no emission i={idx} p={pause}, e={len(self.getEmitPoints())}")
                    return (end_time, time_left)
            else:
                # we first emit at vertex at due time, if we had a mark, we WRITE it.
                has_mark = pos.getMark()
                pos2 = pos.copy()  # then if we had a mark, we ERASE IT so that it does not get copied each time
                emit_time = curr_time + time_to_next_emit
                if has_mark is not None and has_already_mark(has_mark):
                    if debug_pause:
                        logger.debug(f"mark: {has_mark} already present")
                    pos2.setMark(None) # clean mark during pause, otherwise it gets replicated each time...
                    must_spit_out = False  # already spit
                emit_point(idx, pos2, emit_time, reason, False)
                # then we will pause at vertex long enough until we restart moving at end of pause
                pause_remaining = pause - time_to_next_emit
                if debug_pause:
                    logger.debug(f"start pause: {pause} ({len(self.getEmitPoints())}), mark {has_mark} written")
                pos2.setMark(None) # clean mark during pause, otherwise it gets replicated each time...
                # logger.debug(f"pause at time remaining: {pause_remaining}")
                while pause_remaining > 0:
                    emit_time = emit_time + self.frequency
                    emit_point(idx, pos2, emit_time, reason, False)
                    if debug_pause:
                        logger.debug(f"more pause: {pause_remaining} ({len(self.getEmitPoints())}), no mark written (has mark {has_mark})")
                        debug_pause = False
                    pause_remaining = pause_remaining - self.frequency
                time_left = self.frequency + pause_remaining  # pause_remaining < 0 !
                if emit_details:
                    logger.debug(f"end pause: {time_left} ({len(self.getEmitPoints())}), no mark written (has mark {has_mark})")
                return (emit_time, time_left)

        def probably_equal(a, b):
            same_mark = a.getMark() == b.getMark()
            if same_mark:
                logger.debug(f"probably_equal same mark {a.getMark()}")
            same_lat = (a.lat() - b.lat()) < 0.000001
            if same_lat:
                logger.debug(f"probably_equal same latitude")
            same_lon = (a.lon() - b.lon()) < 0.000001
            if same_lon:
                logger.debug(f"probably_equal same longitude")
            return same_mark and same_lat and same_lon
        #
        #
        #
        if self.move_points is None or len(self.move_points) == 0:
            if self.is_event_service():
                svc = self.getSource()
                logger.debug(f"service {type(svc).__name__} «{svc.label}» has no vehicle, assuming event report only")
                return (True, "Emit::emit: no moves, assuming event report only")
            logger.warning("no move")
            return (False, "Emit::emit: no moves")
        #
        #
        # build emission points
        self.frequency = frequency

        # This is to track a special bug...
        # if hasattr(self.move, "service") and type(self.move.service).__name__ == "BaggageService":
        #     emit_details = True
        #     logger.debug("=" * 150)
        #     logger.debug("=" * 150)

        if self.frequency is None or self.frequency < 1:
            return (False, f"Emit::emit: invalid frequency {self.frequency}")

        self.setEmitPoints([])  # reset if called more than once
        total_dist = 0   # sum of distances between emissions
        total_dist_vtx = 0  # sum of distances between vertices
        total_time = 0   # sum of times between emissions

        curridx = 0
        currpos = self.move_points[curridx]

        if self.emit_type == "service" and currpos.getMark() is not None:
            logger.debug(f"adding {currpos.getMark()}..")


        time_to_next_emit = 0 ## randrange(self.frequency)  # we could actually random from (0..self.frequency) to randomly start broadcast
        # if time_to_next_emit == 0
        #     time_to_next_emit = self.frequency
        first_time_to_next_emit = time_to_next_emit
        logger.debug(f"first_time_to_next_emit: {first_time_to_next_emit}")

        # Add first point, we emit it if time_to_next_emit == 0, we emit if waypt == False
        # if time_to_next_emit != 0:  # otherwise, will be added in first loop
        emit_point(curridx, currpos, total_time, "start", waypt=time_to_next_emit != 0)

        future_emit = self.frequency
        # future_emit = self.frequency - 0.2 * self.frequency + randrange(0.4 * self.frequency)  # random time between emission DANGEROUS!

        while curridx < (len(self.move_points) - 1):
            # We progress one leg at a time, leg is from idx -> idx+1.
            next_vtx = self.move_points[curridx + 1]
            currmark = self.move_points[curridx].getMark()
            nextmark = next_vtx.getMark()

            if emit_details:
                logger.debug(f">>> new vertex: {curridx}, e={len(self.getEmitPoints())} s={self.move_points[curridx].speed()}")
                logger.debug(f"current vertex has mark={currmark}")

            if emit_details and self.emit_type == "service": # and next_vtx.getMark() is not None:
                logger.debug(f"next vertex has mark={nextmark}")

            time_to_next_vtx = time_distance_to_next_vtx(currpos, curridx)
            if emit_details:
                logger.debug(f"curridx={curridx}: {time_to_next_emit} sec to next emit, {time_to_next_vtx} sec to next vertex")
            ## logger.debug("START: %d: %f sec to next emit, %f sec to next vertex" % (curridx, time_to_next_emit, time_to_next_vtx))

            must_spit_out = False
            if nextmark is not None:
                if time_to_next_vtx < time_to_next_emit:
                    # We will reach the next vertex before we need to emit
                    # So we must make sure we output the next vertex at least without emiting
                    # or with emission if EMIT_AT_VERTEX is True
                    if emit_details:
                        logger.debug(f"must spit out {nextmark}")
                    must_spit_out = True
                else:
                    if emit_details:
                        logger.debug(f"will reach next emit in {time_to_next_emit} before next vertex {time_to_next_vtx}")

            if time_to_next_vtx <= 0:
                # may be we did not move since last vertex
                if time_to_next_vtx < 0:
                    logger.warning(f"time to next vertex {time_to_next_vtx} < 0, rounding to 0, need to emit vertex..")
                    time_to_next_vtx = 0
                else:
                    if emit_details:
                        logger.debug(f"time to next vertex {time_to_next_vtx} = 0, need to emit vertex..")
                emit_point(curridx, next_vtx, total_time, f"at vertex { curridx + 1 }, e={len(self.getEmitPoints())}", not BROADCAST_AT_VERTEX)  # ONLY IF BROADCAST AT VERTEX
                currpos = next_vtx
                pause = currpos.getProp(FEATPROP.PAUSE.value)
                if pause is not None and pause > 0:
                    total_time, time_to_next_emit = pause_at_vertex(total_time, time_to_next_emit, pause, curridx, next_vtx, total_time, f"pause at vertex { curridx + 1 }")
                    if emit_details:
                        logger.debug(f".. done pausing at vertex. {time_to_next_emit} sec left before next emit")
                else:
                    if emit_details:
                        logger.debug(f".. done emitting vertex (no pause {pause}).")

            if time_to_next_emit == 0:  # need to emit now
                if emit_details:
                    logger.debug(f"time to emit now.. ({curridx}, {time_to_next_emit}, {time_to_next_vtx})")  # if we are here, we know we will not reach the next vertex
                emit_point(curridx, currpos, total_time, f"time to emit now at {curridx}")
                time_to_next_emit = future_emit
                if emit_details:
                    logger.debug(f"done emiting now. continuing..")  # if we are here, we know we will not reach the next vertex
                continue

            # need handling of time_to_next_vtx == 0.

            if (time_to_next_emit > 0) and (time_to_next_emit < future_emit) and (time_to_next_emit < time_to_next_vtx):
                # We need to emit before next vertex
                if emit_details:
                    logger.debug(f"moving on edge with time remaining to next emit.. ({curridx}, {time_to_next_emit}, {time_to_next_vtx})")  # if we are here, we know we will not reach the next vertex
                ## logger.debug("EBEFV: %d: %f sec to next emit, %f sec to next vertex" % (curridx, time_to_next_emit, time_to_next_vtx))
                newpos = destinationOnTrack(currpos, time_to_next_emit, curridx)
                total_time = total_time + time_to_next_emit
                controld = distance(currpos, newpos) * 1000  # km
                total_dist = total_dist + controld
                emit_point(curridx, newpos, total_time, f"moving on edge {curridx} with time remaining to next emit e={len(self.getEmitPoints())}")
                currpos = newpos
                time_to_next_vtx = time_distance_to_next_vtx(currpos, curridx)
                time_to_next_emit = future_emit
                if emit_details:
                    logger.debug(f"..done moving on edge with time remaining to next emit. {time_to_next_emit} sec left before next emit, {time_to_next_vtx} to next vertex")

                if time_to_next_vtx <= 0:
                    # We just emitted and we are at the next vertex.
                    if time_to_next_vtx < 0:
                        logger.warning(f"time to next vertex {time_to_next_vtx} < 0, rounding to 0, need to emit vertex.. 2")
                        time_to_next_vtx = 0
                    else:
                        if emit_details:
                            logger.debug(f"time to next vertex {time_to_next_vtx} = 0, need to emit vertex.. 2")
                    emit_point(curridx, next_vtx, total_time, f"at vertex { curridx + 1 }, e={len(self.getEmitPoints())}", not BROADCAST_AT_VERTEX)  # ONLY IF BROADCAST AT VERTEX
                    currpos = next_vtx
                    pause = currpos.getProp(FEATPROP.PAUSE.value)
                    if pause is not None and pause > 0:
                        total_time, time_to_next_emit = pause_at_vertex(total_time, time_to_next_emit, pause, curridx, next_vtx, total_time, f"pause at vertex { curridx + 1 }")
                        if emit_details:
                            logger.debug(f".. 2 done pausing at vertex. {time_to_next_emit} sec left before next emit")
                    else:
                        if emit_details:
                            logger.debug(f".. done emitting vertex (no pause {pause}).")


            if emit_details:
                logger.debug(f"CHECKPOINT: time_to_next_emit={time_to_next_emit}, future_emit={future_emit}, time_to_next_vtx={time_to_next_vtx}")

            if (time_to_next_emit > 0) and (time_to_next_emit < future_emit) and (time_to_next_vtx < time_to_next_emit):
                # We will reach next vertex before we need to emit
                ##logger.debug("RVBFE: %d: %f sec to next emit, %f sec to next vertex" % (curridx, time_to_next_emit, time_to_next_vtx))
                if emit_details:
                    logger.debug(f"moving to next vertex with time remaining before next emit.. ({curridx}, time_to_next_emit={time_to_next_emit}, time_to_next_vtx={time_to_next_vtx})")  # if we are here, we know we will not reach the next vertex
                total_time = total_time + time_to_next_vtx
                controld = distance(currpos, next_vtx) * 1000  # km
                total_dist = total_dist + controld
                emit_point(curridx, next_vtx, total_time, f"at vertex { curridx + 1 }, e={len(self.getEmitPoints())}", not BROADCAST_AT_VERTEX)  # ONLY IF BROADCAST AT VERTEX
                currpos = next_vtx
                time_to_next_emit = time_to_next_emit - time_to_next_vtx  # time left before next emit
                pause = currpos.getProp(FEATPROP.PAUSE.value)
                if pause is not None and pause > 0:
                    total_time, time_to_next_emit = pause_at_vertex(total_time, time_to_next_emit, pause, curridx, next_vtx, total_time, f"pause at vertex { curridx + 1 }")
                    logger.debug(f".. done pausing at vertex. {time_to_next_emit} sec left before next emit")
                if emit_details:
                    logger.debug(f"..done moving to next vertex with time remaining before next emit. {time_to_next_emit} sec left before next emit, moving to next vertex")

            else:
                # We will emit before we reach next vertex
                if emit_details:
                    logger.debug(f"will not reach next vertex before we need to emit.")
                while time_to_next_vtx > future_emit:  # @todo: >= ?
                    ## logger.debug("EONTR: %d: %f sec to next emit, %f sec to next vertex" % (curridx, time_to_next_emit, time_to_next_vtx))
                    # We keep having time to emit before we reach the next vertex
                    if emit_details:
                        logger.debug("moving on edge.. %d, %f, %f" % (curridx, time_to_next_vtx, future_emit))
                    total_time = total_time + future_emit
                    nextpos = destinationOnTrack(currpos, future_emit, curridx)
                    controld = distance(currpos, nextpos) * 1000  # km
                    total_dist = total_dist + controld
                    emit_point(curridx, nextpos, total_time, f"en route after vertex {curridx}, e={len(self.getEmitPoints())}")
                    currpos = nextpos
                    time_to_next_vtx = time_distance_to_next_vtx(currpos, curridx)
                    time_to_next_emit = future_emit
                    if emit_details:
                        # logger.debug(f"2vtx={time_to_next_vtx}, 2emt={time_to_next_emit}")
                        logger.debug(f".. done moving on edge by {time_to_next_emit} sec. {time_to_next_vtx} remaining to next vertex")

                if time_to_next_vtx > 0:
                    # jump to next vertex because time_to_next_vtx <= future_emit
                    ## logger.debug("TONXV: %d: %f sec to next emit, %f sec to next vertex" % (curridx, time_to_next_emit, time_to_next_vtx))
                    controld = distance(currpos, next_vtx) * 1000  # km
                    if emit_details:
                        logger.debug(f"jumping to next vertex.. ({controld} m, {time_to_next_vtx} sec)")
                    total_time = total_time + time_to_next_vtx
                    controld = distance(currpos, next_vtx) * 1000  # km
                    total_dist = total_dist + controld
                    emit_point(curridx, next_vtx, total_time, f"at vertex { curridx + 1 }, e={len(self.getEmitPoints())}", not BROADCAST_AT_VERTEX)  # ONLY IF BROADCAST AT VERTEX
                    currpos = next_vtx
                    time_to_next_emit = time_to_next_emit - time_to_next_vtx  # time left before next emit
                    pause = currpos.getProp(FEATPROP.PAUSE.value)
                    if pause is not None and pause > 0:
                        total_time, time_to_next_emit = pause_at_vertex(total_time, time_to_next_emit, pause, curridx, next_vtx, total_time, f"pause at vertex { curridx + 1 }, e={len(self.getEmitPoints())}")
                        logger.debug(f".. done pausing at vertex. {time_to_next_emit} sec left before next emit")
                    if emit_details:
                        logger.debug(f".. done jumping to next vertex. {time_to_next_emit} sec left before next emit")

            if must_spit_out:
                logger.warning(f"mark {nextmark} not emitted")

            controld = distance(self.move_points[curridx], next_vtx) * 1000  # km
            total_dist_vtx = total_dist_vtx + controld  # sum of distances between vertices
            if emit_details:
                logger.debug(f"<<< {curridx}: {round(total_time, 2)} sec , {round(total_dist/1000,3)} m / {round(total_dist_vtx/1000, 3)} m\n")
            curridx = curridx + 1

        # need to add last point??
        movemark = self.move_points[-1].getMark()
        emitmark = self._emit_points[-1].getMark()
        logger.debug(f"end points: move:{movemark}, emit:{emitmark}")
        if movemark != emitmark:
            logger.debug(f"end point not added, adding (move:{movemark}, emit:{emitmark})")
            emit_point(len(self.move_points) - 1, currpos, total_time, "end", time_to_next_emit == 0)

        # need to remove deplicate first point?
        # this is created by above algorithm, duplicate does not exists in movement, only in emit
        if probably_equal(self._emit_points[0], self._emit_points[1]):
            del self._emit_points[0]
            logger.debug(f"removed duplicate first point")

        # Restriction
        # If frequency is high, we have thousands of points.
        # So let's suppose we are close to the managed airport.
        # => We limit high frequency emits to the vicinity of the airport.
        # @todo: It would be better to not generate the emission at the first place...
        # Somehow, the test has to be made somewhere. Let's assume filter() is efficient.
        if RATE_LIMIT is not None and frequency < RATE_LIMIT and EMIT_RANGE is not None:
            if self.move is not None:
                if self.move.airport is not None:
                    center = self.move.airport  # yeah, it's a Feature
                    before = len(self.getEmitPoints())
                    self.setEmitPoints( list(filter(lambda f: distance(f, center) < EMIT_RANGE, self.getEmitPoints()))  )
                    logger.warning(f"rate { self.frequency } high, limiting to { EMIT_RANGE }km around airport center: before: {before}, after: {len(self.getEmitPoints())}")
                else:
                    logger.warning(f"rate { self.frequency } high, cannot locate airport")

        # transfert common data to each emit point for emission
        # (may be should think about a FeatureCollection-level property to avoid repetition.)
        if len(self.props) > 0:
            # p = dict(flatdict.FlatDict(self.props))
            self.props["emit"] = self.getInfo() # update meta data about this emission
            p = self.props
            for f in self.getEmitPoints():
                f.addProps(p)
            logger.debug(f"added { len(p) } properties to { len(self.getEmitPoints()) } features")

        res = compute_headings(self.getEmitPoints())
        if not res[0]:
            logger.warning("problem computing headings")
            return res

        res = self.interpolate()
        if not res[0]:
            logger.warning("problem interpolating")
            return res

        # logger.debug("summary: %f vs %f sec, %f vs %f km, %d vs %d" % (round(total_time, 2), round(self.move_points[-1].time(), 2), round(total_dist/1000, 3), round(total_dist_vtx/1000, 3), len(self.move_points), len(self.getEmitPoints())))
        # logger.debug("summary: %s vs %s, %f vs %f km, %d vs %d" % (timedelta(seconds=total_time), timedelta(seconds=round(self.move_points[-1].time(), 2)), round(total_dist/1000, 3), round(total_dist_vtx/1000, 3), len(self.move_points), len(self.getEmitPoints())))
        ####logger.debug(f"summary: {timedelta(seconds=total_time)} vs {timedelta(seconds=self.move_points[-1].time())}, {round(total_dist/1000, 3)} vs {round(total_dist_vtx/1000, 3)} km, {len(self.move_points)} vs {len(self.getEmitPoints())}")
        move_marks = self.move.getMarkList()
        emit_marks = self.getMarkList()
        # emit_moves_marks = self.getMoveMarkList()
        # if self.emit_type == "service"
        if len(move_marks) != len(emit_marks):
            logger.warning(f"move mark list differs from emit mark list (first_time_to_next_emit={first_time_to_next_emit})")

            logger.debug(f"move mark list (len={len(move_marks)}): {move_marks}")
            miss = list(filter(lambda f: f not in move_marks, emit_marks))
            logger.debug(f"not in move list: {miss}")
            # logger.debug(f"emit.move_points (move.getMovePoints()) mark list (len={len(emit_moves_marks)}): {emit_moves_marks}")

            logger.debug(f"emit mark list (len={len(emit_marks)}): {emit_marks}")
            miss = list(filter(lambda f: f not in emit_marks, move_marks))
            logger.debug(f"not in emit list: {miss}")
            self.write_debug("emit")

        logger.debug(f"generated {len(self.getEmitPoints())} points")
        # printFeatures(self.getEmitPoints(), "emit_point", True)
        self.version = self.version + 1
        return (True, "Emit::emit completed")


    def interpolate(self):
        """
        Compute interpolated values for altitude and speed based on distance.
        This is a simple linear interpolation based on distance between points.
        Runs for flight portion of flight.
        Added 13/4/22: First element of array *must* have the property we interpolate set.
        """
        to_interp = self.getEmitPoints()
        # before = []
        check = "vspeed"
        logger.debug(f"{self.getId()}: interpolating ..")
        for name in ["speed", "vspeed", "altitude"]:
            logger.debug(f".. {name} ..")
            if name == check:
                before = list(map(lambda x: x.getProp(name), to_interp))
            x = to_interp[0].getProp(name)
            if x is not None:  # first element has value set
                status = doInterpolation(to_interp, name)
            else:
                if self.emit_type not in ["service", "mission"] or name == "speed":
                    logger.warning(f"{self.getId()}: first value has no property {name}, do not interpolate")
                continue
            if not status[0]:
                logger.warning(status[1])
        logger.debug(f"{self.getId()}: .. done.")

        x = to_interp[0].getProp(FEATPROP.ALTITUDE.value)  # get the property, not the third coord.
        if x is not None:
            logger.debug(f"{self.getId()}: checking and transposing altitudes to geojson coordinates..")
            for f in to_interp:
                if len(f["geometry"]["coordinates"]) == 2:
                    a = f.altitude()
                    if a is not None:
                        f["geometry"]["coordinates"].append(float(a))
                    else:
                        logger.warning(f"no altitude? {f.getProp(FEATPROP.EMIT_INDEX.value)}.")
            logger.debug(f"{self.getId()}: .. done.")
        else:
            # may be we should then set altitude to the airport
            if self.emit_type not in ["service", "mission"]:
                logger.warning(f"{self.getId()}: first value has no altitude, do not interpolate")

        logger.debug(f"{self.getId()}: computing headings..")
        res = compute_headings(self.getEmitPoints())
        if not res[0]:
            logger.warning("problem computing headings")
            return res
        logger.debug(f"{self.getId()}: .. done.")

        # name = check
        # for i in range(len(to_interp)):
        #     v = to_interp[i].getProp(name) if to_interp[i].getProp(name) is not None and to_interp[i].getProp(name) != "None" else "none"
        #     logger.debug("%d: %s -> %s." % (i, before[i] if before[i] is not None else -1, v))


        # logger.debug("last point %d: %f, %f" % (len(self.move_points), self.move_points[-1].speed(), self.move_points[-1].altitude()))
        # i = 0
        # for f in self.move_points:
        #     s = f.speed()
        #     a = f.altitude()
        #     logger.debug("alter: %d: %f %f" % (i, s if s is not None else -1, a if a is not None else -1))
        #     i = i + 1

        return (True, "Emit::interpolated speed and altitude")


    # def getMarkList(self):
    #     l = set()
    #     [l.add(f.getMark()) for f in self.getEmitPoints()]
    #     if None in l:
    #         l.remove(None)
    #     return l


    def getMoveMarkList(self):
        l = set()
        [l.add(f.getMark()) for f in self.move_points]
        if None in l:
            l.remove(None)
        return l


    def getTimedMarkList(self):
        l = dict()

        if self._scheduled_points is None or len(self._scheduled_points) == 0:
            return l

        output = io.StringIO()
        print("\n", file=output)
        print(f"TIMED MARK LIST", file=output)
        MARK_LIST = ["mark", "relative", "time"]
        table = []

        for f in self._scheduled_points:
            m = f.getMark()
            if m is not None:
                if m in l:
                    l[m]["count"] = l[m]["count"] + 1 if "count" in l[m] else 2
                else:
                    l[m] = {
                        "rel": f.getProp(FEATPROP.EMIT_REL_TIME.value),
                        "ts": f.getProp(FEATPROP.EMIT_ABS_TIME.value),
                        "dt": f.getProp(FEATPROP.EMIT_ABS_TIME_FMT.value)
                    }
                line = []
                line.append(m)
                line.append(f.getProp(FEATPROP.EMIT_REL_TIME.value))
                line.append(datetime.fromtimestamp(f.getProp(FEATPROP.EMIT_ABS_TIME.value)).astimezone().replace(microsecond = 0))
                table.append(line)
                # logger.debug(f"{m.rjust(25)}: t={t:>7.1f}: {f.getProp(FEATPROP.EMIT_ABS_TIME_FMT.value)}")

        table = sorted(table, key=lambda x: x[2])  # absolute emission time
        print(tabulate(table, headers=MARK_LIST), file=output)

        contents = output.getvalue()
        output.close()
        logger.debug(f"{contents}")

        return l


    def addToPause(self, sync, duration: float, add: bool = True):
        f = findFeatures(self.move_points, {FEATPROP.MARK.value: sync})
        if f is not None and len(f) > 0:
            r = f[0]
            s = r.speed()
            if s is not None and s > 0:
                logger.warning(f"speed {s}m/sec at vertex is not 0")
            before = r.getProp(FEATPROP.PAUSE.value) if (r.getProp(FEATPROP.PAUSE.value) is not None and add) else 0
            r.setPause(before + duration)
            logger.debug(f"found {sync} mark, added {duration} sec. pause for a total of {r.getProp(FEATPROP.PAUSE.value)}")
        # should recompute emit
        if self.getEmitPoints() is not None:  # if already computed before, we need to recompute it
           self.emit(self.frequency)


    def setPause(self, sync, duration: float):
        self.addToPause(sync=sync, duration=duration, add=False)


    def schedule(self, sync, moment: datetime, do_print: bool = False):
        """
        """
        if self.is_event_service():
            return (True, "Emit::schedule: no need to save event service")

        dt_provided = True
        if moment is None:
            dt_provided = False
            moment = self.getSource().getEstimatedTime()
            if moment is None:
                return (False, "Emit::schedule: no scheduled time")

        if self.emit_id is None:
            logger.debug(f"no emit id")
            return (False, f"Emit::schedule no emit id")

        # logger.debug(f"mark list: {self.getMarkList()}")
        self.curr_schedule = moment
        self.curr_syncmark = sync

        offset = self.getRelativeEmissionTime(sync)
        if offset is not None:
            offset = int(offset)  # pylint E1130
            self.offset_name = sync
            self.offset = offset
            logger.debug(f"{self.offset_name} offset {self.offset} sec")
            when = moment + timedelta(seconds=(- offset))
            self.curr_starttime = when
            logger.debug(f"emit_point starts at {when} ({when.timestamp()})")
            self._scheduled_points = []  # brand new scheduling, reset previous one
            for e in self.getEmitPoints():
                p = EmitPoint.new(e)
                t = e.getProp(FEATPROP.EMIT_REL_TIME.value)
                if t is not None:
                    when = moment + timedelta(seconds=(t - offset))
                    p.setProp(FEATPROP.EMIT_ABS_TIME.value, when.timestamp())
                    p.setProp(FEATPROP.EMIT_ABS_TIME_FMT.value, when.isoformat())
                    # logger.debug(f"done at {when.timestamp()}")
                self._scheduled_points.append(p)
            logger.debug(f"emit_point finishes at {when} ({when.timestamp()}) ({len(self._scheduled_points)} positions)")
            # now that we have "absolute time", we update the parent
            ret = self.updateEstimatedTime(update_source=dt_provided)
            if not ret[0]:
                return ret
            # May be should not do it here...
            # ret = self.scheduleMessages(sync, moment)
            # if not ret[0]:
            #     return ret
            # For debugging purpose only:
            if do_print:
                dummy = self.getTimedMarkList()
            return (True, "Emit::schedule completed")

        logger.warning(f"{sync} mark not found")
        return (False, f"Emit::schedule {sync} mark not found")


    def scheduleMessages(self, sync, moment: datetime, do_print: bool = False):
        dt_provided = True
        if moment is None:
            dt_provided = False
            moment = self.getSource().getEstimatedTime()
            if moment is None:
                return (False, "Emit::scheduleMessages: no scheduled time")

        output = io.StringIO()

        print("\n", file=output)
        print(f"SYNCHRONIZATION: {sync} at {moment}", file=output)
        print(f"TIMED MESSAGE LIST", file=output)
        MARK_LIST = ["type", "message", "sync", "offset", "rel. to sync", "total", "time"]
        table = []

        logger.debug(f"{self.getId()}: {sync} at {moment}, scheduling..")
        t0 = moment
        offset = self.getRelativeEmissionTime(sync)
        if offset is not None:
            t0 = moment + timedelta(seconds=(- offset))
            logger.debug(f"{self.getId()}: t=0 at {t0}..")
        else:
            logger.warning(f"{self.getId()}: {sync} mark not found, using moment with no offset")
        # t0 is ON/OFF BLOCK time
        for m in self.getMessages():
            when = t0
            offset = 0
            total = 0
            if m.relative_sync is not None:
                offset = self.getRelativeEmissionTime(m.relative_sync)
                if offset is not None:
                    when = t0 + timedelta(seconds=offset)
                    total = offset + m.relative_time
                    logger.debug(f"{self.getId()}: {m.relative_sync} offset={offset}sec, total={total}")
                else:
                    logger.warning(f"{self.getId()}: {m.relative_sync} mark not found, using moment with no offset")
            else:
                logger.debug(f"{self.getId()}: no relative sync, using ON/OFF BLOCK time")
            m.schedule(when)
            line = []
            line.append(m.getType())
            line.append(m.getText())
            line.append(m.relative_sync)
            line.append(offset)
            line.append(m.relative_time)
            line.append(total)
            line.append(m.getAbsoluteEmissionTime().replace(microsecond = 0))
            table.append(line)
        logger.debug(f"..scheduled")
        table = sorted(table, key=lambda x: x[6])  # absolute emission time()
        print(tabulate(table, headers=MARK_LIST), file=output)
        contents = output.getvalue()
        output.close()
        if do_print:
            logger.debug(f"{contents}")
        return (True, "Emit::scheduleMessages completed")


    def getTimeBracket(self, as_string: bool = False):
        if self._scheduled_points is not None and len(self._scheduled_points) > 0:
            start = self._scheduled_points[0].getAbsoluteEmissionTime()
            end   = self._scheduled_points[-1].getAbsoluteEmissionTime()
            if not as_string:
                return (start, end)
            startdt = datetime.fromtimestamp(start, tz=timezone.utc)
            enddt = datetime.fromtimestamp(end, tz=timezone.utc)
            return (startdt.isoformat(), enddt.isoformat())
        logger.debug(f"{self.getId()}: no emit point")
        return (None, None)


    def getFeatureAt(self, sync: str):
        f = findFeatures(self._scheduled_points, {FEATPROP.MARK.value: sync})
        if f is not None and len(f) > 0:
            logger.debug(f"found {sync}")
            return f[0]
        logger.warning(f"{sync} not found in emission")
        return None


    def getAbsoluteEmissionTime(self, sync: str):
        """
        Gets the absolute emission time.
        Returns UNIX timestamp.
        :param      sync:  The synchronize
        :type       sync:  str
        """
        f = self.getFeatureAt(sync)
        if f is not None:
            return f.getAbsoluteEmissionTime()
        logger.warning(f"no feature at {sync}")
        return None


    def getEstimatedTime(self):
        """
        Gets the time of the start of the source move for departure/mission/service
        or the end of the source move for arrival
        """
        mark = None
        if self.emit_type == MOVE_TYPE.FLIGHT.value:
            is_arrival = self.getSource().is_arrival()
            mark = FLIGHT_PHASE.TOUCH_DOWN.value if is_arrival else FLIGHT_PHASE.TAKE_OFF.value
        elif self.emit_type == MOVE_TYPE.SERVICE.value:
            mark = SERVICE_PHASE.SERVICE_START.value
        elif self.emit_type == MOVE_TYPE.MISSION.value:
            mark = MISSION_PHASE.START.value

        if mark is not None:
            f = self.getAbsoluteEmissionTime(mark)
            if f is not None:
                # localtz = Timezone(offset=MANAGED_AIRPORT["tzoffset"], name=MANAGED_AIRPORT["tzname"])
                return datetime.fromtimestamp(f, tz=timezone.utc)
            else:
                logger.warning(f"no feature at mark {mark}")
        else:
            logger.warning(f"no mark")

        logger.warning(f"could not estimate")
        return None


    def updateEstimatedTime(self, update_source: bool = True):
        """
        Copies the estimated time into source movement.
        """
        et = self.getEstimatedTime()
        if et is not None:
            source = self.getSource()
            if update_source:
                source.setEstimatedTime(dt=et)
            self.updateResources(et)
            logger.debug(f"estimated {source.getId()}: {et.isoformat()}")
            return (True, "Emit::updateEstimatedTime updated")

        logger.warning(f"no estimated time")
        return (True, "Emit::updateEstimatedTime not updated")


    def updateResources(self, et: datetime):
        source = self.getSource()
        is_arrival = None

        if source is None:
            return (False, "Emit::updateResources no source")

        if self.emit_type == MOVE_TYPE.FLIGHT.value:
            fid = source.getId()
            is_arrival = source.is_arrival()
            am = source.managedAirport.airport.manager
            rwy = source.runway.getResourceId()
            et_from = et - timedelta(minutes=3)
            et_to   = et + timedelta(minutes=3)
            rwrsc = am.runway_allocator.findReservation(rwy, fid)
            if rwrsc is not None:
                rwrsc.setEstimatedTime(et_from, et_to)
                logger.debug(f"updated {rwy} for {fid}")
            else:
                logger.warning(f"no reservation found for runway {rwy}")

            ramp = source.ramp.getResourceId()
            if is_arrival:
                et_from = et
                et_to   = et + timedelta(minutes=150)
            else:
                et_from = et - timedelta(minutes=150)
                et_to   = et
            rprsc = am.ramp_allocator.findReservation(ramp, fid)
            if rprsc is not None:
                rprsc.setEstimatedTime(et_from, et_to)
                logger.debug(f"updated {ramp} for {fid}")
            else:
                logger.warning(f"no reservation found for ramp {ramp}")

        else:  # service, mission
            ident = source.getId()
            vehicle = source.vehicle
            am = self.move.airport.manager

            svrsc = am.equipment_allocator.findReservation(vehicle.getResourceId(), ident)
            if svrsc is not None:
                et_end = et + timedelta(minutes=30)
                svrsc.setEstimatedTime(et, et_end)
                logger.debug(f"updated {vehicle.getResourceId()} for {ident}")
            else:
                logger.warning(f"no reservation found for vehicle {vehicle.getResourceId()}")

        logger.debug(f"resources not updated")

        return (True, "Emit::updateResources updated")
