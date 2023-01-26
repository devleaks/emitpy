"""
Emit instance is a list of EmitPoints to broadcast along the Movement path.
The instance is partially passivated in a cache and can be recovered with sufficient
information.
"""
import os
import json
import logging

from datetime import datetime, timedelta, timezone
from random import randrange
from geojson import Feature, FeatureCollection
from geojson.geometry import Geometry
from turfpy.measurement import distance, bearing, destination

from redis.commands.json.path import Path

from emitpy.geo import FeatureWithProps, cleanFeatures, findFeatures, Movement, asLineString, toTraffic
from emitpy.utils import interpolate as doInterpolation, compute_headings, key_path, Timezone
from emitpy.message import Messages, EstimatedTimeMessage

from emitpy.constants import FLIGHT_DATABASE, SLOW_SPEED, FEATPROP, FLIGHT_PHASE, SERVICE_PHASE, MISSION_PHASE
from emitpy.constants import REDIS_DATABASE, REDIS_TYPE, REDIS_DATABASES
from emitpy.constants import RATE_LIMIT, EMIT_RANGE, MOVE_TYPE
from emitpy.constants import DEFAULT_FREQUENCY, GSE_EMIT_WHEN_STOPPED
from emitpy.parameters import MANAGED_AIRPORT_AODB

logger = logging.getLogger("Emit")


BROADCAST_AT_VERTEX = False
must_spit_out = False

class EmitPoint(FeatureWithProps):
    """
    An EmitPoint is a Feature<Point> with additional information for emission.
    All information to be emited in included into the EmitPoint.
    """
    def __init__(self, geometry: Geometry, properties: dict):
        FeatureWithProps.__init__(self, geometry=geometry, properties=properties)

    def getRelativeEmissionTime(self):
        t = self.getProp(FEATPROP.EMIT_REL_TIME.value)
        return t if t is not None else 0

    def getAbsoluteEmissionTime(self):
        t = self.getProp(FEATPROP.EMIT_ABS_TIME.value)
        return t if t is not None else 0


class Emit(Messages):
    """
    Emit takes an array of MovePoints to produce a FeatureCollection of decorated features ready for emission.
    """
    def __init__(self, move: Movement):
        Messages.__init__(self)
        self.move = move

        self.moves = None
        self.emit_id = None
        self.emit_type = None
        self.emit_meta = None
        self.format = None
        self.frequency = None  # seconds
        self._emit = []  # [ EmitPoint ], time-relative emission of messages
        self.scheduled_emit = []  # [ EmitPoint ], a copy of self._emit but with actual emission time (absolute time)
        self.props = {}  # general purpose properties added to each emit point
        self.version = 0
        self.offset_name = None
        self.offset = None

        if type(self).__name__ == "Emit" and move is None:
            logger.error(":init: move cannot be None for new Emit")

        if move is not None:
            # We create an emit from a movement
            self.emit_id = self.move.getId()
            m = self.move.getInfo()
            self.emit_type = m["type"] if "type" in m else REDIS_DATABASE.UNKNOWN.value
            # self.emit_meta = EmitMeta()
            self.moves = self.move.getMoves()
            self.props = self.move.getInfo()  # collect common props from movement
            self.props["emit"] = self.getInfo() # add meta data about this emission
            # logger.debug(f":__init__: {len(self.moves)} move points to emit with props {json.dumps(self.props, indent=2)}")
            logger.debug(f":__init__: {len(self.moves)} move points to emit with {len(self.props)} properties")
        # else:
            # We reconstruct an emit from cache/database
        #     self.emit_meta = EmitMeta.find({"emit_id": self.emit_id})
        #     logger.debug(f":__init__: loaded {len(self.moves)} emit points from cache")


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
            "type": "emit",
            "emit-type": self.emit_type if self.emit_type is not None else ty,
            "ident": self.emit_id,
            "frequency": self.frequency,
            "time-bracket": self.getTimeBracket(as_string=True),
            "version": self.version
        }


    def getSource(self):
        if self.move is not None:
            return self.move.getSource()
        logger.error(":getSource: no movement")
        return None


    def getMessages(self):
        m = super().getMessages()  # this emit's messages
        logger.debug(f":getMessages: added super()")
        if self.move is not None:
            m = m + self.move.getMessages()
            logger.debug(f":getMessages: added source")
        return m


    def getMeta(self):
        """
        Emit identifier augmented with data from the movement.
        """
        # logger.debug(f":getMeta: from Emit")
        self.emit_meta = self.getInfo()
        self.emit_meta["props"] = self.props
        self.emit_meta["marks"] = self.getTimedMarkList()
        source = self.getSource()
        if source is not None:
            self.emit_meta["move"] = source.getInfo()
            self.emit_meta["time"] = source.getScheduleHistory(as_string=True)
        # logger.debug(f":getMeta: {self.emit_meta}")
        return self.emit_meta


    def getKey(self, extension: str):
        db = REDIS_DATABASE.UNKNOWN.value
        if self.emit_type in REDIS_DATABASES.keys():
            db = REDIS_DATABASES[self.emit_type]
        else:
            logger.warning(f":getKey: invalid type {self.emit_type}, database unknown")
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
            logger.debug(f":loadMeta: ..got {len(self.props)} props")
        else:
            logger.debug(f":loadMeta: ..no meta for {self.emit_type}")
        return (True, "Emit::loadMeta loaded")


    def saveMeta(self, redis):
        meta_id = self.getKey(REDIS_TYPE.EMIT_META.value)
        redis.delete(meta_id)
        redis.json().set(meta_id, Path.root_path(), self.getMeta())
        logger.debug(f":saveMeta: .. meta saved {meta_id}")
        return (True, "Emit::saveMeta saved")


    def save(self, redis):
        """
        Save flight paths to file for emitted positions.
        """
        if redis is None:
            # return self.saveFile()
            return (True, "Emit::save: no Redis")

        if self._emit is None or len(self._emit) == 0:
            logger.warning(":save: no emission point")
            return (False, "Emit::save: no emission point")

        emit_id = self.getKey(REDIS_TYPE.EMIT.value)

        # 1. Save emission points
        emit = {}
        for f in self._emit:
            emit[json.dumps(f)] = f.getProp(FEATPROP.EMIT_REL_TIME.value)
        redis.delete(emit_id)
        redis.zadd(emit_id, emit)
        move_id = self.getKey("")

        # 2. Save KML (for flights only)
        # if callable(getattr(self.move, "getKML", None)):
        #     kml_id = self.getKey(REDIS_TYPE.EMIT_KML.value)
        #     redis.set(kml_id, self.move.getKML())
        #     logger.debug(f":save: saved kml")

        # 3. Save messages for broadcast
        mid = self.getKey(REDIS_TYPE.EMIT_MESSAGE.value)
        for m in self.getMessages():
            redis.sadd(mid, json.dumps(m.getInfo()))
        logger.debug(f":save: saved {redis.scard(mid)} messages")

        logger.debug(f":save: saved {move_id}")
        return self.saveMeta(redis)


    def write_debug(self):
        logger.warning(":write_debug: writing debug files..")
        basedir = os.path.join(MANAGED_AIRPORT_AODB, "debug")
        if not os.path.exists(basedir):
            os.mkdir(basedir)
            logger.info(f":write_debug: directory {basedir} does not exist. created.")

        # Try to save situation...
        ident = self.getId()
        fnbase = os.path.join(basedir, f"debug-{ident}-{datetime.now().isoformat()}-")
        self.move.saveFile()
        with open(fnbase + "meta.out", "w") as fp:
            json.dump(self.getMeta(), fp, indent=4)
        with open(fnbase + "debug-emit-info.out", "w") as fp:
            json.dump(self.getInfo(), fp, indent=4)
        with open(fnbase + "debug-emit-data.geojson", "w") as fp:
            json.dump(FeatureCollection(features=cleanFeatures(self._emit)), fp, indent=4)
        with open(fnbase + "debug-move-info.out", "w") as fp:
            json.dump(self.move.getInfo(), fp, indent=4)
        with open(fnbase + "debug-move-emit-data.geojson", "w") as fp:
            json.dump(FeatureCollection(features=cleanFeatures(self.moves)), fp, indent=4)
        with open(fnbase + "debug-move-move-data.geojson", "w") as fp:
            json.dump(FeatureCollection(features=cleanFeatures(self.move.moves)), fp, indent=4)
        logger.warning(f":write_debug: ..written debug files {fnbase}")


    def saveFile(self):
        """
        Save flight paths to file for emitted positions.
        """
        ident = self.getId()
        db = REDIS_DATABASES[self.emit_type] if self.emit_type in REDIS_DATABASES.keys() else REDIS_DATABASE.UNKNOWN.value
        basedir = os.path.join(MANAGED_AIRPORT_AODB, db)
        if not os.path.exists(basedir):
            os.mkdir(basedir)
            logger.info(f":saveFile: directory {basedir} did not exist. created.")

        basename = os.path.join(basedir, ident)
        # 1. Save "raw emits"
        # filename = os.path.join(basename + "-5-emit.json")
        # with open(filename, "w") as fp:
        #     json.dump(self._emit, fp, indent=4)

        # 2. Save "raw emits" and linestring
        # ls = Feature(geometry=asLineString(self._emit))
        # filename = os.path.join(basename + "-5-emit_ls.geojson")
        # with open(filename, "w") as fp:
        #     json.dump(FeatureCollection(features=cleanFeatures(self._emit)+ [ls]), fp, indent=4)

        # 3. Save linestring with timestamp
        # Save for traffic analysis
        logger.debug(f":saveFile: {self.getInfo()}")
        logger.debug(f":saveFile: emit_point={len(self.scheduled_emit)} positions")

        if self.scheduled_emit is None or len(self.scheduled_emit) == 0:
            logger.warning(":saveFile: no scheduled emission point")
            self.write_debug()
            return (False, "Emit::saveFile: no scheduled emission point")

        logger.debug(f":saveFile: ***** there are {len(self.scheduled_emit)} points")

        ls = toTraffic(self.scheduled_emit)
        filename = os.path.join(basename + "-traffic.csv")
        with open(filename, "w") as fp:
            fp.write(ls)

        logger.debug(f":saveFile: saved {ident}")
        return (True, "Emit::saveFile saved")


    def emit(self, frequency: int):
        # Utility subfunctions
        global must_spit_out
        must_spit_out = False
        emit_details = False

        def has_already_mark(mark: str) -> bool:
            for e in self._emit:
                if e.getMark() == mark:
                    return True
            return False

        def point_on_line(c, n, d):
            # brng = bearing(c, n)
            # dest = destination(c, d / 1000, brng, {"units": "km"})
            # if emit_details:
            #     logger.debug(f":point_on_line: d={d})")
            return FeatureWithProps.convert(destination(c, d / 1000, bearing(c, n), {"units": "km"}))

        def time_distance_to_next_vtx(c0, idx):  # time it takes to go from c0 to vtx[idx+1]
            totald = distance(self.moves[idx], self.moves[idx+1])  * 1000  # km
            if totald == 0:  # same point...
                # logger.debug(f":time_distance_to_next_vtx: same point i={idx}? Did not move?")
                return 0
            partiald = distance(self.moves[idx], c0) * 1000  # km
            if partiald > totald:  # yes, it happens...
                logger.warning(":time_distance_to_next_vtx: partiald > totald? forcing partiald = totald")
                return 0

            portion = partiald / totald
            leftd = totald - partiald  # = distance(c0, self.moves[idx+1])
            v0 = self.moves[idx].speed()
            v1 = self.moves[idx+1].speed()
            v = v0 + portion * (v1 - v0)
            # logger.debug(f":time_distance_to_next_vtx: {round(leftd, 3)}, verif={round(distance(c0, self.moves[idx+1])*1000, 3)}")
            v = max(v, SLOW_SPEED)
            t = 0
            if (v + v1) != 0:
                t = 2 * leftd / (v + v1)
            else:
                logger.warning(":emit:time_distance_to_next_vtx: v + v1 = 0?")
            # logger.debug(f":time_distance_to_next_vtx: {idx}, tot={totald}, left={leftd}, t={t})")
            # logger.debug(f":time_distance_to_next_vtx: done={partiald} ({portion}), v={v}, v0={v0}, v1={v1})")
            return t

        def destinationOnTrack(c0, duration, idx):  # from c0, moves duration seconds on edges at speed specified at vertices
            totald = distance(self.moves[idx], self.moves[idx+1]) * 1000  # km
            if totald == 0:  # same point...
                logger.warning(f":emit:destinationOnTrack: same point i={idx}?")
                return None
            partiald = distance(self.moves[idx], c0) * 1000  # km
            portion = partiald / totald
            v0 = self.moves[idx].speed()
            v1 = self.moves[idx+1].speed()
            v = v0 + portion * (v1 - v0)
            v = max(v, SLOW_SPEED)

            acc = (v1 * v1 - v0 * v0) / (2 * totald)  # a=(u²-v²)/2d
            hourrate = duration  # / 3600
            dist = v * hourrate + acc * hourrate * hourrate / 2

            # nextpos = point_on_line(currpos, self.moves[idx+1], dist)
            # controld = distance(currpos, nextpos) * 1000  # km
            # logger.debug(":destinationOnTrack: (%d, v=%f, dur=%f, dist=%f, seglen=%f)" % (idx, v, duration, controld, totald))
            # return nextpos
            return point_on_line(currpos, self.moves[idx+1], dist)

        def emit_point(idx, pos, time, reason, waypt=False):
            global must_spit_out
            e = EmitPoint.new(pos)
            e.setProp(FEATPROP.EMIT_REL_TIME.value, time)
            e.setProp(FEATPROP.EMIT_INDEX.value, len(self._emit))  # Sets unique index on emit features
            e.setProp(FEATPROP.BROADCAST.value, not waypt)
            if self.emit_type == "service" and e.getMark() is not None: # and e.getMark() is not None:
                logger.debug(f":emit_point: added mark={e.getMark()}, reason={reason}, emit={e.getProp(FEATPROP.BROADCAST.value)}")

            # if GSE_EMIT_WHEN_STOPPED:
            #     e.setProp(FEATPROP.BROADCAST.value, not waypt)
            # else:
            #     e.setProp(FEATPROP.BROADCAST.value, not waypt and e.speed(0) > 0)
            if not e.hasColor():
                if waypt:
                    e.setColor("#eeeeee")
                    # logger.debug(f":emit:emit_point:waypoint: {reason} i={idx} t={time} ({timedelta(seconds=time)}) s={e.speed()}")
                else:
                    e.setColor("#ccccff")
                    # logger.debug(f":emit:emit_point: {reason} i={idx} t={time} ({timedelta(seconds=time)}) s={e.speed()}")
            self._emit.append(e)
            if e.getMark() is not None:
                must_spit_out = False
                if emit_details:
                    logger.debug(f":emit_point: split out {e.getMark()}")
            # logger.debug(f":emit:emit_point: dist2nvtx={round(distance(e, self.moves[idx+1])*1000,1)} i={idx} e={len(self._emit)}")

        def pause_at_vertex(curr_time, time_to_next_emit, pause: float, idx, pos, time, reason):
            global must_spit_out
            debug_pause = False
            if emit_details:
                logger.debug(f":pause_at_vertex: pause i={idx} p={pause}, e={len(self._emit)}")
            if pause < self.frequency:  # may be emit before reaching next vertex:
                if pause > time_to_next_emit:  # neet to emit before we reach next vertex
                    emit_time = curr_time + time_to_next_emit
                    emit_point(idx, pos, emit_time, reason, False) # waypt=False to emit
                    end_time = curr_time + pause
                    time_left = self.frequency - (pause - time_to_next_emit)
                    if emit_details:
                        logger.debug(f":pause_at_vertex: pause before next emit: emit at vertex i={idx} p={pause}, e={len(self._emit)}")
                    return (end_time, time_left)
                else:  # pause a little but not enough to emit
                    end_time = curr_time + pause
                    time_left = time_to_next_emit - pause
                    if emit_details:
                        logger.debug(f":pause_at_vertex: pause a little but do not emit at vertex: no emission i={idx} p={pause}, e={len(self._emit)}")
                    return (end_time, time_left)
            else:
                # we first emit at vertex at due time, if we had a mark, we WRITE it.
                has_mark = pos.getMark()
                pos2 = pos.copy()  # then if we had a mark, we ERASE IT so that it does not get copied each time
                emit_time = curr_time + time_to_next_emit
                if has_mark is not None and has_already_mark(has_mark):
                    if debug_pause:
                        logger.debug(f":pause_at_vertex: mark: {has_mark} already present")
                    pos2.setMark(None) # clean mark during pause, otherwise it gets replicated each time...
                    must_spit_out = False  # already spit
                emit_point(idx, pos2, emit_time, reason, False)
                # then we will pause at vertex long enough until we restart moving at end of pause
                pause_remaining = pause - time_to_next_emit
                if debug_pause:
                    logger.debug(f":pause_at_vertex: start pause: {pause} ({len(self._emit)}), mark {has_mark} written")
                pos2.setMark(None) # clean mark during pause, otherwise it gets replicated each time...
                # logger.debug(f":pause_at_vertex: pause at time remaining: {pause_remaining}")
                while pause_remaining > 0:
                    emit_time = emit_time + self.frequency
                    emit_point(idx, pos2, emit_time, reason, False)
                    if debug_pause:
                        logger.debug(f":pause_at_vertex: more pause: {pause_remaining} ({len(self._emit)}), no mark written (has mark {has_mark})")
                        debug_pause = False
                    pause_remaining = pause_remaining - self.frequency
                time_left = self.frequency + pause_remaining  # pause_remaining < 0 !
                if emit_details:
                    logger.debug(f":pause_at_vertex: end pause: {time_left} ({len(self._emit)}), no mark written (has mark {has_mark})")
                return (emit_time, time_left)
        #
        #
        #
        if self.moves is None or len(self.moves) == 0:
            logger.warning(":emit: no move")
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

        self._emit = []  # reset if called more than once
        total_dist = 0   # sum of distances between emissions
        total_dist_vtx = 0  # sum of distances between vertices
        total_time = 0   # sum of times between emissions

        curridx = 0
        currpos = self.moves[curridx]

        if self.emit_type == "service" and currpos.getMark() is not None:
            logger.debug(f":emit: adding {currpos.getMark()}..")


        time_to_next_emit = 0 ## randrange(self.frequency)  # we could actually random from (0..self.frequency) to randomly start broadcast
        # if time_to_next_emit == 0
        #     time_to_next_emit = self.frequency
        first_time_to_next_emit = time_to_next_emit
        logger.debug(f":emit: first_time_to_next_emit: {first_time_to_next_emit}")

        # Add first point, we emit it if time_to_next_emit == 0, we emit if waypt == False
        # if time_to_next_emit != 0:  # otherwise, will be added in first loop
        emit_point(curridx, currpos, total_time, "start", waypt=time_to_next_emit != 0)

        future_emit = self.frequency
        # future_emit = self.frequency - 0.2 * self.frequency + randrange(0.4 * self.frequency)  # random time between emission DANGEROUS!

        while curridx < (len(self.moves) - 1):
            # We progress one leg at a time, leg is from idx -> idx+1.
            next_vtx = self.moves[curridx + 1]
            currmark = self.moves[curridx].getMark()
            nextmark = next_vtx.getMark()

            if emit_details:
                logger.debug(f":emit: >>> new vertex: {curridx}, e={len(self._emit)} s={self.moves[curridx].speed()}")
                logger.debug(f":emit: current vertex has mark={currmark}")

            if emit_details and self.emit_type == "service": # and next_vtx.getMark() is not None:
                logger.debug(f":emit: next vertex has mark={nextmark}")

            time_to_next_vtx = time_distance_to_next_vtx(currpos, curridx)
            if emit_details:
                logger.debug(f":emit: curridx={curridx}: {time_to_next_emit} sec to next emit, {time_to_next_vtx} sec to next vertex")
            ## logger.debug(":emit: START: %d: %f sec to next emit, %f sec to next vertex" % (curridx, time_to_next_emit, time_to_next_vtx))

            must_spit_out = False
            if nextmark is not None:
                if time_to_next_vtx < time_to_next_emit:
                    # We will reach the next vertex before we need to emit
                    # So we must make sure we output the next vertex at least without emiting
                    # or with emission if EMIT_AT_VERTEX is True
                    if emit_details:
                        logger.debug(f":emit: must spit out {nextmark}")
                    must_spit_out = True
                else:
                    if emit_details:
                        logger.debug(f":emit: will reach next emit in {time_to_next_emit} before next vertex {time_to_next_vtx}")

            if time_to_next_vtx <= 0:
                # may be we did not move since last vertex
                if time_to_next_vtx < 0:
                    logger.warning(f":emit: time to next vertex {time_to_next_vtx} < 0, rounding to 0, need to emit vertex..")
                    time_to_next_vtx = 0
                else:
                    if emit_details:
                        logger.debug(f":emit: time to next vertex {time_to_next_vtx} = 0, need to emit vertex..")
                emit_point(curridx, next_vtx, total_time, f"at vertex { curridx + 1 }, e={len(self._emit)}", not BROADCAST_AT_VERTEX)  # ONLY IF BROADCAST AT VERTEX
                currpos = next_vtx
                pause = currpos.getProp(FEATPROP.PAUSE.value)
                if pause is not None and pause > 0:
                    total_time, time_to_next_emit = pause_at_vertex(total_time, time_to_next_emit, pause, curridx, next_vtx, total_time, f"pause at vertex { curridx + 1 }")
                    if emit_details:
                        logger.debug(f":emit: .. done pausing at vertex. {time_to_next_emit} sec left before next emit")
                else:
                    if emit_details:
                        logger.debug(f":emit: .. done emitting vertex (no pause {pause}).")

            if time_to_next_emit == 0:  # need to emit now
                if emit_details:
                    logger.debug(f":emit: time to emit now.. ({curridx}, {time_to_next_emit}, {time_to_next_vtx})")  # if we are here, we know we will not reach the next vertex
                emit_point(curridx, currpos, total_time, f"time to emit now at {curridx}")
                time_to_next_emit = future_emit
                if emit_details:
                    logger.debug(f":emit: done emiting now. continuing..")  # if we are here, we know we will not reach the next vertex
                continue

            # need handling of time_to_next_vtx == 0.

            if (time_to_next_emit > 0) and (time_to_next_emit < future_emit) and (time_to_next_emit < time_to_next_vtx):
                # We need to emit before next vertex
                if emit_details:
                    logger.debug(f":emit: moving on edge with time remaining to next emit.. ({curridx}, {time_to_next_emit}, {time_to_next_vtx})")  # if we are here, we know we will not reach the next vertex
                ## logger.debug(":emit: EBEFV: %d: %f sec to next emit, %f sec to next vertex" % (curridx, time_to_next_emit, time_to_next_vtx))
                newpos = destinationOnTrack(currpos, time_to_next_emit, curridx)
                total_time = total_time + time_to_next_emit
                controld = distance(currpos, newpos) * 1000  # km
                total_dist = total_dist + controld
                emit_point(curridx, newpos, total_time, f"moving on edge {curridx} with time remaining to next emit e={len(self._emit)}")
                currpos = newpos
                time_to_next_vtx = time_distance_to_next_vtx(currpos, curridx)
                time_to_next_emit = future_emit
                if emit_details:
                    logger.debug(f":emit: ..done moving on edge with time remaining to next emit. {time_to_next_emit} sec left before next emit, {time_to_next_vtx} to next vertex")

                if time_to_next_vtx <= 0:
                    # We just emitted and we are at the next vertex.
                    if time_to_next_vtx < 0:
                        logger.warning(f":emit: time to next vertex {time_to_next_vtx} < 0, rounding to 0, need to emit vertex.. 2")
                        time_to_next_vtx = 0
                    else:
                        if emit_details:
                            logger.debug(f":emit: time to next vertex {time_to_next_vtx} = 0, need to emit vertex.. 2")
                    emit_point(curridx, next_vtx, total_time, f"at vertex { curridx + 1 }, e={len(self._emit)}", not BROADCAST_AT_VERTEX)  # ONLY IF BROADCAST AT VERTEX
                    currpos = next_vtx
                    pause = currpos.getProp(FEATPROP.PAUSE.value)
                    if pause is not None and pause > 0:
                        total_time, time_to_next_emit = pause_at_vertex(total_time, time_to_next_emit, pause, curridx, next_vtx, total_time, f"pause at vertex { curridx + 1 }")
                        if emit_details:
                            logger.debug(f":emit: .. 2 done pausing at vertex. {time_to_next_emit} sec left before next emit")
                    else:
                        if emit_details:
                            logger.debug(f":emit: .. done emitting vertex (no pause {pause}).")


            if emit_details:
                logger.debug(f":emit: CHECKPOINT: time_to_next_emit={time_to_next_emit}, future_emit={future_emit}, time_to_next_vtx={time_to_next_vtx}")

            if (time_to_next_emit > 0) and (time_to_next_emit < future_emit) and (time_to_next_vtx < time_to_next_emit):
                # We will reach next vertex before we need to emit
                ##logger.debug(":emit: RVBFE: %d: %f sec to next emit, %f sec to next vertex" % (curridx, time_to_next_emit, time_to_next_vtx))
                if emit_details:
                    logger.debug(f"moving to next vertex with time remaining before next emit.. ({curridx}, time_to_next_emit={time_to_next_emit}, time_to_next_vtx={time_to_next_vtx})")  # if we are here, we know we will not reach the next vertex
                total_time = total_time + time_to_next_vtx
                controld = distance(currpos, next_vtx) * 1000  # km
                total_dist = total_dist + controld
                emit_point(curridx, next_vtx, total_time, f"at vertex { curridx + 1 }, e={len(self._emit)}", not BROADCAST_AT_VERTEX)  # ONLY IF BROADCAST AT VERTEX
                currpos = next_vtx
                time_to_next_emit = time_to_next_emit - time_to_next_vtx  # time left before next emit
                pause = currpos.getProp(FEATPROP.PAUSE.value)
                if pause is not None and pause > 0:
                    total_time, time_to_next_emit = pause_at_vertex(total_time, time_to_next_emit, pause, curridx, next_vtx, total_time, f"pause at vertex { curridx + 1 }")
                    logger.debug(f":emit: .. done pausing at vertex. {time_to_next_emit} sec left before next emit")
                if emit_details:
                    logger.debug(f":emit: ..done moving to next vertex with time remaining before next emit. {time_to_next_emit} sec left before next emit, moving to next vertex")

            else:
                # We will emit before we reach next vertex
                if emit_details:
                    logger.debug(f":emit: will not reach next vertex before we need to emit.")
                while time_to_next_vtx > future_emit:  # @todo: >= ?
                    ## logger.debug(":emit: EONTR: %d: %f sec to next emit, %f sec to next vertex" % (curridx, time_to_next_emit, time_to_next_vtx))
                    # We keep having time to emit before we reach the next vertex
                    if emit_details:
                        logger.debug(":emit: moving on edge.. %d, %f, %f" % (curridx, time_to_next_vtx, future_emit))
                    total_time = total_time + future_emit
                    nextpos = destinationOnTrack(currpos, future_emit, curridx)
                    controld = distance(currpos, nextpos) * 1000  # km
                    total_dist = total_dist + controld
                    emit_point(curridx, nextpos, total_time, f"en route after vertex {curridx}, e={len(self._emit)}")
                    currpos = nextpos
                    time_to_next_vtx = time_distance_to_next_vtx(currpos, curridx)
                    time_to_next_emit = future_emit
                    if emit_details:
                        # logger.debug(f"2vtx={time_to_next_vtx}, 2emt={time_to_next_emit}")
                        logger.debug(f":emit: .. done moving on edge by {time_to_next_emit} sec. {time_to_next_vtx} remaining to next vertex")

                if time_to_next_vtx > 0:
                    # jump to next vertex because time_to_next_vtx <= future_emit
                    ## logger.debug(":emit: TONXV: %d: %f sec to next emit, %f sec to next vertex" % (curridx, time_to_next_emit, time_to_next_vtx))
                    controld = distance(currpos, next_vtx) * 1000  # km
                    if emit_details:
                        logger.debug(f":emit: jumping to next vertex.. ({controld} m, {time_to_next_vtx} sec)")
                    total_time = total_time + time_to_next_vtx
                    controld = distance(currpos, next_vtx) * 1000  # km
                    total_dist = total_dist + controld
                    emit_point(curridx, next_vtx, total_time, f"at vertex { curridx + 1 }, e={len(self._emit)}", not BROADCAST_AT_VERTEX)  # ONLY IF BROADCAST AT VERTEX
                    currpos = next_vtx
                    time_to_next_emit = time_to_next_emit - time_to_next_vtx  # time left before next emit
                    pause = currpos.getProp(FEATPROP.PAUSE.value)
                    if pause is not None and pause > 0:
                        total_time, time_to_next_emit = pause_at_vertex(total_time, time_to_next_emit, pause, curridx, next_vtx, total_time, f"pause at vertex { curridx + 1 }, e={len(self._emit)}")
                        logger.debug(f":emit: .. done pausing at vertex. {time_to_next_emit} sec left before next emit")
                    if emit_details:
                        logger.debug(f":emit: .. done jumping to next vertex. {time_to_next_emit} sec left before next emit")

            if must_spit_out:
                logger.warning(f":emit: mark {nextmark} not emitted")

            controld = distance(self.moves[curridx], next_vtx) * 1000  # km
            total_dist_vtx = total_dist_vtx + controld  # sum of distances between vertices
            if emit_details:
                logger.debug(f":emit: <<< {curridx}: {round(total_time, 2)} sec , {round(total_dist/1000,3)} m / {round(total_dist_vtx/1000, 3)} m\n")
            curridx = curridx + 1

        # need to add last point??
        movemark = self.moves[-1].getMark()
        emitmark = self._emit[-1].getMark()
        logger.debug(f":emit: end points: {movemark}, {emitmark}")
        if movemark != emitmark:
            logger.debug(f":emit: end point not added, adding ({movemark}, {emitmark})")
            emit_point(len(self.moves) - 1, currpos, total_time, "end", time_to_next_emit == 0)

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
                    before = len(self._emit)
                    self._emit = list(filter(lambda f: distance(f, center) < EMIT_RANGE, self._emit))
                    logger.warning(f":emit: rate { self.frequency } high, limiting to { EMIT_RANGE }km around airport center: before: {before}, after: {len(self._emit)}")
                else:
                    logger.warning(f":emit: rate { self.frequency } high, cannot locate airport")

        # transfert common data to each emit point for emission
        # (may be should think about a FeatureCollection-level property to avoid repetition.)
        if len(self.props) > 0:
            # p = dict(flatdict.FlatDict(self.props))
            self.props["emit"] = self.getInfo() # update meta data about this emission
            p = self.props
            for f in self._emit:
                f.addProps(p)
            logger.debug(f":emit: added { len(p) } properties to { len(self._emit) } features")

        res = compute_headings(self._emit)
        if not res[0]:
            logger.warning(":emit: problem computing headings")
            return res

        res = self.interpolate()
        if not res[0]:
            logger.warning(":emit: problem interpolating")
            return res

        # logger.debug(":emit: summary: %f vs %f sec, %f vs %f km, %d vs %d" % (round(total_time, 2), round(self.moves[-1].time(), 2), round(total_dist/1000, 3), round(total_dist_vtx/1000, 3), len(self.moves), len(self._emit)))
        # logger.debug(":emit: summary: %s vs %s, %f vs %f km, %d vs %d" % (timedelta(seconds=total_time), timedelta(seconds=round(self.moves[-1].time(), 2)), round(total_dist/1000, 3), round(total_dist_vtx/1000, 3), len(self.moves), len(self._emit)))
        ####logger.debug(f":emit: summary: {timedelta(seconds=total_time)} vs {timedelta(seconds=self.moves[-1].time())}, {round(total_dist/1000, 3)} vs {round(total_dist_vtx/1000, 3)} km, {len(self.moves)} vs {len(self._emit)}")
        move_marks = self.move.getMarkList()
        emit_marks = self.getMarkList()
        # emit_moves_marks = self.getMoveMarkList()
        # if self.emit_type == "service"
        if len(move_marks) != len(emit_marks):
            logger.warning(f":emit: move mark list differs from emit mark list (first_time_to_next_emit={first_time_to_next_emit})")

            logger.debug(f":emit: move mark list (len={len(move_marks)}): {move_marks}")
            miss = list(filter(lambda f: f not in move_marks, emit_marks))
            logger.debug(f":emit: not in move list: {miss}")
            # logger.debug(f":emit: emit.moves (move.getMoves()) mark list (len={len(emit_moves_marks)}): {emit_moves_marks}")

            logger.debug(f":emit: emit mark list (len={len(emit_marks)}): {emit_marks}")
            miss = list(filter(lambda f: f not in emit_marks, move_marks))
            logger.debug(f":emit: not in emit list: {miss}")
            self.write_debug()

        logger.debug(f":emit: generated {len(self._emit)} points")
        # printFeatures(self._emit, "emit_point", True)
        self.version = self.version + 1
        return (True, "Emit::emit completed")


    def interpolate(self):
        """
        Compute interpolated values for altitude and speed based on distance.
        This is a simple linear interpolation based on distance between points.
        Runs for flight portion of flight.
        Added 13/4/22: First element of array *must* have the property we interpolate set.
        """
        to_interp = self._emit
        # before = []
        check = "vspeed"
        logger.debug(f":interpolate: {self.getId()}: interpolating ..")
        for name in ["speed", "vspeed", "altitude"]:
            logger.debug(f":interpolate: .. {name} ..")
            if name == check:
                before = list(map(lambda x: x.getProp(name), to_interp))
            x = to_interp[0].getProp(name)
            if x is not None:  # first element has value set
                status = doInterpolation(to_interp, name)
            else:
                if self.emit_type not in ["service", "mission"] or name == "speed":
                    logger.warning(f":interpolate: {self.getId()}: first value has no property {name}, do not interpolate")
                continue
            if not status[0]:
                logger.warning(status[1])
        logger.debug(f":interpolate: {self.getId()}: .. done.")

        x = to_interp[0].getProp(FEATPROP.ALTITUDE.value)  # get the property, not the third coord.
        if x is not None:
            logger.debug(f":interpolate: {self.getId()}: checking and transposing altitudes to geojson coordinates..")
            for f in to_interp:
                if len(f["geometry"]["coordinates"]) == 2:
                    a = f.altitude()
                    if a is not None:
                        f["geometry"]["coordinates"].append(float(a))
                    else:
                        logger.warning(f":interpolate: no altitude? {f['properties']['emit-index']}.")
            logger.debug(f":interpolate: {self.getId()}: .. done.")
        else:
            # may be we should then set altitude to the airport
            if self.emit_type not in ["service", "mission"]:
                logger.warning(f":interpolate: {self.getId()}: first value has no altitude, do not interpolate")

        logger.debug(f":interpolate: {self.getId()}: computing headings..")
        res = compute_headings(self._emit)
        if not res[0]:
            logger.warning(":emit: problem computing headings")
            return res
        logger.debug(f":interpolate: {self.getId()}: .. done.")

        # name = check
        # for i in range(len(to_interp)):
        #     v = to_interp[i].getProp(name) if to_interp[i].getProp(name) is not None and to_interp[i].getProp(name) != "None" else "none"
        #     logger.debug(":interpolate: %d: %s -> %s." % (i, before[i] if before[i] is not None else -1, v))


        # logger.debug(":interpolate: last point %d: %f, %f" % (len(self.moves), self.moves[-1].speed(), self.moves[-1].altitude()))
        # i = 0
        # for f in self.moves:
        #     s = f.speed()
        #     a = f.altitude()
        #     logger.debug(":vnav: alter: %d: %f %f" % (i, s if s is not None else -1, a if a is not None else -1))
        #     i = i + 1

        return (True, "Emit::interpolated speed and altitude")


    def getMarkList(self):
        l = set()
        [l.add(f.getMark()) for f in self._emit]
        if None in l:
            l.remove(None)
        return l


    def getMoveMarkList(self):
        l = set()
        [l.add(f.getMark()) for f in self.moves]
        if None in l:
            l.remove(None)
        return l


    def getTimedMarkList(self):
        l = dict()
        for f in self.scheduled_emit:
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
        return l


    def addToPause(self, sync, duration: float, add: bool = True):
        f = findFeatures(self.moves, {FEATPROP.MARK.value: sync})
        if f is not None and len(f) > 0:
            r = f[0]
            s = r.speed()
            if s is not None and s > 0:
                logger.warning(f":addToPause: speed {s}m/sec at vertex is not 0")
            before = r.getProp(FEATPROP.PAUSE.value) if (r.getProp(FEATPROP.PAUSE.value) is not None and add) else 0
            r.setPause(before + duration)
            logger.debug(f":addToPause: found {sync} mark, added {duration} sec. pause for a total of {r.getProp(FEATPROP.PAUSE.value)}")
        # should recompute emit
        if self._emit is not None:  # if already computed before, we need to recompute it
           self.emit(self.frequency)


    def setPause(self, sync, duration: float):
        self.addToPause(sync=sync, duration=duration, add=False)


    def schedule(self, sync, moment: datetime):
        """
        Adjust a emission track to synchronize moment at position mkar synch.
        This should only change the EMIT_ABS_TIME property.

        :param      sync:   The synchronize
        :type       sync:   { string }
        :param      moment:  The moment
        :type       moment:  datetime
        """
        if self.emit_id is None:
            logger.debug(f":schedule: no emit id")
            return (False, f"Emit::schedule no emit id")

        logger.debug(f":schedule: mark list: {self.getMarkList()}")

        offset = self.getRelativeEmissionTime(sync)
        if offset is not None:
            self.offset_name = sync
            self.offset = offset
            logger.debug(f":schedule: {self.offset_name} offset {self.offset} sec")
            when = moment + timedelta(seconds=(- offset))
            logger.debug(f":schedule: emit_point starts at {when} ({when.timestamp()})")
            self.scheduled_emit = []  # brand new scheduling, reset previous one
            for e in self._emit:
                p = EmitPoint.new(e)
                t = e.getProp(FEATPROP.EMIT_REL_TIME.value)
                if t is not None:
                    when = moment + timedelta(seconds=(t - offset))
                    p.setProp(FEATPROP.EMIT_ABS_TIME.value, when.timestamp())
                    p.setProp(FEATPROP.EMIT_ABS_TIME_FMT.value, when.isoformat())
                    # logger.debug(f":get: done at {when.timestamp()}")
                self.scheduled_emit.append(p)
            logger.debug(f":schedule: emit_point finishes at {when} ({when.timestamp()}) ({len(self.scheduled_emit)} positions)")
            # now that we have "absolute time", we update the parent
            ret = self.updateEstimatedTime()
            if not ret[0]:
                return ret
            ret = self.scheduleMessages(sync, moment)
            if not ret[0]:
                logger.warning(f":schedule: scheduleMessages returned {ret[1]}, ignoring")
            return (True, "Emit::schedule completed")

        logger.warning(f":schedule: {sync} mark not found")
        return (False, f"Emit::schedule {sync} mark not found")


    def scheduleMessages(self, sync, moment: datetime):
        logger.debug(f":scheduleMessages: {sync} at {moment}..")
        for m in self.getMessages():
            when = moment
            if m.relative_sync is not None:
                offset = self.getRelativeEmissionTime(m.relative_sync)
                if offset is not None:
                    when = moment + timedelta(seconds=(- offset))
                    logger.debug(f":scheduleMessages: {m.relative_sync} offset={offset}sec")
                else:
                    logger.warning(f":scheduleMessages: {m.relative_sync} mark not found, using moment with no offset")
            m.schedule(when)
        logger.debug(f":scheduleMessages: ..scheduled")
        return (True, "Emit::scheduleMessages completed")


    def getTimeBracket(self, as_string: bool = False):
        if self.scheduled_emit is not None and len(self.scheduled_emit) > 0:
            start = self.scheduled_emit[0].getAbsoluteEmissionTime()
            end   = self.scheduled_emit[-1].getAbsoluteEmissionTime()
            if not as_string:
                return (start, end)
            startdt = datetime.fromtimestamp(start, tz=timezone.utc)
            enddt = datetime.fromtimestamp(end, tz=timezone.utc)
            return (startdt.isoformat(), enddt.isoformat())
        logger.debug(f":getTimeBracket: no emit point")
        return (None, None)


    def getFeatureAt(self, sync: str):
        f = findFeatures(self.scheduled_emit, {FEATPROP.MARK.value: sync})
        if f is not None and len(f) > 0:
            logger.debug(f":getFeatureAt: found {sync}")
            return f[0]
        logger.warning(f":getFeatureAt: {sync} not found in emission")
        return None


    def getRelativeEmissionTime(self, sync: str):
        f = findFeatures(self._emit, {FEATPROP.MARK.value: sync})
        if f is not None and len(f) > 0:
            r = f[0]
            logger.debug(f":getRelativeEmissionTime: found {sync}")
            offset = r.getProp(FEATPROP.EMIT_REL_TIME.value)
            if offset is not None:
                return offset
            else:
                logger.warning(f":schedule: {FEATPROP.MARK.value} {sync} has no time offset, using 0")
                return 0
        logger.warning(f":getRelativeEmissionTime: {sync} not found in emission ({self.getMarkList()})")
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
        logger.warning(f":getAbsoluteEmissionTime: no feature at {sync}")
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
                logger.warning(f":getEstimatedTime: no feature at mark {mark}")
        else:
            logger.warning(f":getEstimatedTime: no mark")

        logger.warning(f":getEstimatedTime: could not estimate")
        return None


    def updateEstimatedTime(self):
        """
        Copies the estimated time into source movement.
        """
        et = self.getEstimatedTime()
        if et is not None:
            source = self.getSource()
            source.setEstimatedTime(dt=et)
            self.updateResources(et)
            logger.debug(f":updateEstimatedTime: estimated {source.getId()}: {et.isoformat()}")
            return (True, "Emit::updateEstimatedTime updated")

        logger.warning(f":updateEstimatedTime: no estimated time")
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

            TIME_NEW_ET_ADVANCE_WARNING=-1800
            self.addMessage(EstimatedTimeMessage(flight_id=fid,
                                                 is_arrival=is_arrival,
                                                 scheduled_time=et,
                                                 relative_time=TIME_NEW_ET_ADVANCE_WARNING,
                                                 et=et))
            logger.debug(f":updateResources: sent new estimate message {fid}: {et}")


            rwy = source.runway.getResourceId()
            et_from = et - timedelta(minutes=3)
            et_to   = et + timedelta(minutes=3)
            rwrsc = am.runway_allocator.findReservation(rwy, fid)
            if rwrsc is not None:
                rwrsc.setEstimatedTime(et_from, et_to)
                logger.debug(f":updateResources: updated {rwy} for {fid}")
            else:
                logger.warning(f":updateResources: no reservation found for runway {rwy}")

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
                logger.debug(f":updateResources: updated {ramp} for {fid}")
            else:
                logger.warning(f":updateResources: no reservation found for ramp {ramp}")

        else:  # service, mission
            ident = source.getId()
            vehicle = source.vehicle
            am = self.move.airport.manager

            svrsc = am.equipment_allocator.findReservation(vehicle.getResourceId(), ident)
            if svrsc is not None:
                et_end = et + timedelta(minutes=30)
                svrsc.setEstimatedTime(et, et_end)
                logger.debug(f":updateResources: updated {vehicle.getResourceId()} for {ident}")
            else:
                logger.warning(f":updateResources: no reservation found for vehicle {vehicle.getResourceId()}")

        logger.debug(f":updateResources: resources not updated")

        return (True, "Emit::updateResources updated")
