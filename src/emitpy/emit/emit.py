"""
Emit instance is a list of EmitPoints to broadcast along the Movement path.
The instance is partially passivated in a cache and can be recovered with sufficient
information.
"""
import os
import json
import flatdict
import logging

from datetime import datetime, timedelta
from random import randrange
from typing import Mapping
from geojson import Feature, FeatureCollection, Point, LineString
from geojson.geometry import Geometry
from turfpy.measurement import distance, bearing, destination

from redis.commands.json.path import Path
from redis_om import HashModel

from emitpy.geo import FeatureWithProps, cleanFeatures, printFeatures, findFeatures, Movement, asLineString
from emitpy.utils import interpolate as doInterpolation, compute_headings, key_path
from emitpy.utils import FT, Messages, EstimatedTimeMessage

from emitpy.constants import MANAGED_AIRPORT, FLIGHT_DATABASE, SLOW_SPEED, FEATPROP, FLIGHT_PHASE, SERVICE_PHASE, MISSION_PHASE
from emitpy.constants import REDIS_DATABASE, REDIS_TYPE, REDIS_DATABASES
from emitpy.constants import RATE_LIMIT, EMIT_RANGE
from emitpy.parameters import AODB_DIR, REDIS_CONNECT

from .emitmeta import EmitMeta


logger = logging.getLogger("Emit")



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
        self.frequency = 30  # seconds
        self._emit = []  # [ EmitPoint ], time-relative emission of messages
        self.scheduled_emit = []  # [ EmitPoint ], a copy of self._emit but with actual emission time (absolute time)
        self.props = {}  # general purpose properties added to each emit point
        self.version = 0
        self.offset_name = None
        self.offset = None

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
            logger.debug(f":__init__: {len(self.moves)} move points to emit with {len(self.props)} props")
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
        return {
            "type": "emit",
            "subtype": self.emit_type if self.emit_type is not None else ty,
            "ident": self.emit_id,
            "frequency": self.frequency,
            "version": self.version
        }


    def getMeta(self):
        """
        Emit identifier augmented with data from the movement.
        """
        meta_data = self.getInfo()
        meta_data["props"] = self.props
        source = self.getSource()
        if source is not None:
            meta_data["move"] = source.getInfo()
            meta_data["time"] = source.getScheduleHistory()
        logger.debug(f":getMeta: {meta_data}")
        return meta_data


    def getSource(self):
        # Abstract class
        if self.move is not None:
            return self.move.getSource()
        return None


    def getKey(self, extension: str):
        db = REDIS_DATABASE.UNKNOWN.value
        if self.emit_type in REDIS_DATABASES.keys():
            db = REDIS_DATABASES[self.emit_type]
        return key_path(db, self.emit_id, extension)


    def loadMeta(self):
        emit_id = self.getKey(REDIS_TYPE.EMIT_META.value)
        if self.redis.exists(emit_id):
            self.redis = json.loads(redis.get(emit_id))
            logger.debug(f":loadFromCache: ..got {len(self.props)} props")
        else:
            logger.debug(f":loadFromCache: ..no meta for {emit_id}")
        return (True, "Emit::saveMeta saved")


    def saveMeta(self, redis):
        meta_id = self.getKey(REDIS_TYPE.EMIT_META.value)
        redis.delete(meta_id)
        redis.json().set(meta_id, Path.root_path(), self.getMeta())
        return (True, "Emit::loadMeta saved")


    def save(self, redis):
        """
        Save flight paths to file for emitted positions.
        """
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
        if callable(getattr(self.move, "getKML", None)):
            kml_id = self.getKey(REDIS_TYPE.EMIT_KML.value)
            redis.set(kml_id, self.move.getKML())
            logger.debug(f":save: saved kml")

        # 3. Save messages for broadcast
        if self.move is not None:
            mid = self.getKey(REDIS_TYPE.EMIT_MESSAGE.value)
            for m in self.move.getMessages():
                redis.sadd(mid, json.dumps(m.getInfo()))
            logger.debug(f":save: saved {redis.scard(mid)} messages")

        logger.debug(f":save: saved {move_id}")
        return self.saveMeta(redis)

    def saveFile(self):
        """
        Save flight paths to file for emitted positions.
        """
        ident = self.getId()
        basename = os.path.join(AODB_DIR, FLIGHT_DATABASE, ident)

        # filename = os.path.join(basename + "-5-emit.json")
        # with open(filename, "w") as fp:
        #     json.dump(self._emit, fp, indent=4)
        ls = Feature(geometry=asLineString(self._emit))
        filename = os.path.join(basename + "-5-emit_ls.geojson")
        with open(filename, "w") as fp:
            json.dump(FeatureCollection(features=cleanFeatures(self._emit)+ [ls]), fp, indent=4)

        logger.debug(f":save: saved {ident}")
        return (True, "Emit::save saved")


    def emit(self, frequency: int = 30):
        # Utility subfunctions
        def point_on_line(c, n, d):
            # brng = bearing(c, n)
            # dest = destination(c, d / 1000, brng, {"units": "km"})
            return FeatureWithProps.convert(destination(c, d / 1000, bearing(c, n), {"units": "km"}))

        def time_distance_to_next_vtx(c0, idx):  # time it takes to go from c0 to vtx[idx+1]
            totald = distance(self.moves[idx], self.moves[idx+1])  * 1000  # km
            if totald == 0:  # same point...
                # logger.warning(f":emit:time_distance_to_next_vtx: same point i={idx}?")
                return 0
            partiald = distance(self.moves[idx], c0) * 1000  # km
            portion = partiald / totald
            leftd = totald - partiald  # = distance(c0, self.moves[idx+1])
            v0 = self.moves[idx].speed()
            v1 = self.moves[idx+1].speed()
            v = v0 + portion * (v1 - v0)
            v = max(v, SLOW_SPEED)

            # logger.debug(f":time_distance_to_next_vtx: {round(leftd, 3)}, verif={round(distance(c0, self.moves[idx+1])*1000, 3)}")

            t = 0
            if (v + v1) != 0:
                t = 2 * leftd / (v + v1)
            else:
                logger.warning(":emit:time_distance_to_next_vtx: v + v1 = 0?")

            # logger.debug(f":time_distance_to_next_vtx: {idx}, tot={totald}, done={partiald}, v={v}, v0={v0}, v1={v1}, t={t})")
            # logger.debug(f":time_distance_to_next_vtx: {idx}, tot={totald}, left={leftd}, t={t})")
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
            #logger.debug(":destinationOnTrack: (%d, v=%f, dur=%f, dist=%f, seglen=%f)" % (idx, v, duration, controld, totald))
            # return nextpos
            return point_on_line(currpos, self.moves[idx+1], dist)

        def emit_point(idx, pos, time, reason, waypt=False):
            e = EmitPoint.new(pos)
            e.setProp(FEATPROP.EMIT_REL_TIME.value, time)
            e.setProp(FEATPROP.EMIT_INDEX.value, len(self._emit))
            e.setProp(FEATPROP.BROADCAST.value, not waypt)
            e.setProp(FEATPROP.EMIT_REASON.value, reason)
            if not e.hasColor():
                if waypt:
                    e.setColor("#eeeeee")
                    # logger.debug(f":emit:emit_point:waypoint: {reason} i={idx} t={time} ({timedelta(seconds=time)}) s={e.speed()}")
                else:
                    e.setColor("#ccccff")
                    # logger.debug(f":emit:emit_point: {reason} i={idx} t={time} ({timedelta(seconds=time)}) s={e.speed()}")
            self._emit.append(e)
            # logger.debug(f":emit:emit_point: dist2nvtx={round(distance(e, self.moves[idx+1])*1000,1)} i={idx} e={len(self._emit)}")

        def pause_at_vertex(curr_time, time_to_next_emit, pause: float, idx, pos, time, reason):
            logger.debug(f":pause_at_vertex: pause i={idx} p={pause}, e={len(self._emit)}")
            if pause < self.frequency:  # may be emit before reaching next vertex:
                if pause > time_to_next_emit:  # neet to emit before we reach next vertex
                    emit_time = curr_time + time_to_next_emit
                    emit_point(idx, pos, emit_time, reason, False) # waypt=False to emit
                    end_time = curr_time + pause
                    time_left = self.frequency - pause - time_to_next_emit
                    # logger.debug(f":pause_at_vertex: pause before next emit: emit at vertex i={idx} p={pause}, e={len(self._emit)}")
                    return (end_time, time_left)
                else:  # pause but carry on later
                    end_time = curr_time + pause
                    time_left = time_to_next_emit - pause
                    # logger.debug(f":pause_at_vertex: pause but do not emit: no emission i={idx} p={pause}, e={len(self._emit)}")
                    return (end_time, time_left)
            else:
                emit_time = curr_time + time_to_next_emit
                emit_point(idx, pos, emit_time, reason, False)
                pause_remaining = pause - time_to_next_emit
                # logger.debug(f":pause_at_vertex: pause at time remaining: {pause_remaining}")
                while pause_remaining > 0:
                    emit_time = emit_time + self.frequency
                    emit_point(idx, pos, emit_time, reason, False)
                    # logger.debug(f":pause_at_vertex: more pause: {pause_remaining}")
                    pause_remaining = pause_remaining - self.frequency
                time_left = pause_remaining + self.frequency
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
        self._emit = []  # reset if called more than once
        total_dist = 0   # sum of distances between emissions
        total_dist_vtx = 0  # sum of distances between vertices
        total_time = 0   # sum of times between emissions

        curridx = 0
        currpos = self.moves[curridx]

        # Add first point
        emit_point(curridx, currpos, total_time, "start")

        time_to_next_emit = randrange(self.frequency)  # we could actually random from (0..self.frequency) to randomly start broadcast

        future_emit = self.frequency
        # future_emit = self.frequency - 0.2 * self.frequency + randrange(0.4 * self.frequency)  # random time between emission DANGEROUS!

        while curridx < (len(self.moves) - 1):
            # We progress one leg at a time, leg is from idx -> idx+1.
            # logger.debug(f":emit: new vertex: {curridx}, e={len(self._emit)} s={self.moves[curridx].speed()}")
            next_vtx = self.moves[curridx + 1]
            time_to_next_vtx = time_distance_to_next_vtx(currpos, curridx)
            # logger.debug(f":emit: >>>> {curridx}: {time_to_next_emit} sec to next emit, {time_to_next_vtx} sec to next vertex")
            ## logger.debug(":emit: START: %d: %f sec to next emit, %f sec to next vertex" % (curridx, time_to_next_emit, time_to_next_vtx))

            if (time_to_next_emit > 0) and (time_to_next_emit < future_emit) and (time_to_next_emit < time_to_next_vtx):
                # We need to emit before next vertex
                # logger.debug(f"moving on edge with time remaining to next emit.. ({curridx}, {time_to_next_emit}, {time_to_next_vtx})")  # if we are here, we know we will not reach the next vertex
                ## logger.debug(":emit: EBEFV: %d: %f sec to next emit, %f sec to next vertex" % (curridx, time_to_next_emit, time_to_next_vtx))
                newpos = destinationOnTrack(currpos, time_to_next_emit, curridx)
                total_time = total_time + time_to_next_emit
                controld = distance(currpos, newpos) * 1000  # km
                total_dist = total_dist + controld
                emit_point(curridx, newpos, total_time, f"moving on edge {curridx} with time remaining to next emit e={len(self._emit)}")
                currpos = newpos
                time_to_next_emit = future_emit
                time_to_next_vtx = time_distance_to_next_vtx(currpos, curridx)
                # logger.debug(f"..done moving on edge with time remaining to next emit. {time_to_next_emit} sec left before next emit, {time_to_next_vtx} to next vertex")

            if (time_to_next_emit > 0) and (time_to_next_emit < future_emit) and (time_to_next_vtx < time_to_next_emit):
                ##logger.debug(":emit: RVBFE: %d: %f sec to next emit, %f sec to next vertex" % (curridx, time_to_next_emit, time_to_next_vtx))
                # We will reach next vertex before we need to emit
                # logger.debug(f"moving from to vertex with time remaining before next emit.. ({curridx}, {time_to_next_emit}, {time_to_next_vtx})")  # if we are here, we know we will not reach the next vertex
                total_time = total_time + time_to_next_vtx
                controld = distance(currpos, next_vtx) * 1000  # km
                total_dist = total_dist + controld
                emit_point(curridx, next_vtx, total_time, f"at vertex { curridx + 1 }, e={len(self._emit)}", True)  # ONLY IF BROADCAST AT VERTEX
                currpos = next_vtx
                time_to_next_emit = time_to_next_emit - time_to_next_vtx  # time left before next emit
                pause = currpos.getProp(FEATPROP.PAUSE.value)
                if pause is not None and pause > 0:
                    total_time, time_to_next_emit = pause_at_vertex(total_time, time_to_next_emit, pause, curridx, next_vtx, total_time, f"pause at vertex { curridx + 1 }")
                    logger.debug(f":emit: .. done pausing at vertex. {time_to_next_emit} sec left before next emit")
                # logger.debug(f"..done moving to next vertex with time remaining before next emit. {time_to_next_emit} sec left before next emit, moving to next vertex")

            else:
                # We will emit before we reach next vertex
                while time_to_next_vtx > future_emit:  # @todo: >= ?
                    ## logger.debug(":emit: EONTR: %d: %f sec to next emit, %f sec to next vertex" % (curridx, time_to_next_emit, time_to_next_vtx))
                    # We keep having time to emit before we reach the next vertex
                    #logger.debug("moving on edge.. %d, %f, %f" % (curridx, time_to_next_vtx, future_emit))
                    total_time = total_time + future_emit
                    nextpos = destinationOnTrack(currpos, future_emit, curridx)
                    controld = distance(currpos, nextpos) * 1000  # km
                    total_dist = total_dist + controld
                    emit_point(curridx, nextpos, total_time, f"en route after vertex {curridx}, e={len(self._emit)}")
                    currpos = nextpos
                    time_to_next_vtx = time_distance_to_next_vtx(currpos, curridx)
                    time_to_next_emit = future_emit
                    # logger.debug(f"2vtx={time_to_next_vtx}, 2emt={time_to_next_emit}")
                    # logger.debug(f".. done moving on edge by {time_to_next_emit} sec. {time_to_next_vtx} remaining to next vertex")

                if time_to_next_vtx > 0:
                    # jump to next vertex because time_to_next_vtx <= future_emit
                    ## logger.debug(":emit: TONXV: %d: %f sec to next emit, %f sec to next vertex" % (curridx, time_to_next_emit, time_to_next_vtx))
                    controld = distance(currpos, next_vtx) * 1000  # km
                    # logger.debug(f"jumping to next vertex.. ({controld} m, {time_to_next_vtx} sec)")
                    total_time = total_time + time_to_next_vtx
                    controld = distance(currpos, next_vtx) * 1000  # km
                    total_dist = total_dist + controld
                    emit_point(curridx, next_vtx, total_time, f"at vertex { curridx + 1 }, e={len(self._emit)}", True)  # ONLY IF BROADCAST AT VERTEX
                    currpos = next_vtx
                    time_to_next_emit = time_to_next_emit - time_to_next_vtx  # time left before next emit
                    pause = currpos.getProp(FEATPROP.PAUSE.value)
                    if pause is not None and pause > 0:
                        total_time, time_to_next_emit = pause_at_vertex(total_time, time_to_next_emit, pause, curridx, next_vtx, total_time, f"pause at vertex { curridx + 1 }, e={len(self._emit)}")
                        logger.debug(f":emit: .. done pausing at vertex. {time_to_next_emit} sec left before next emit")
                    # logger.debug(f".. done jumping to next vertex. {time_to_next_emit} sec left before next emit")

            controld = distance(self.moves[curridx], next_vtx) * 1000  # km
            total_dist_vtx = total_dist_vtx + controld  # sum of distances between vertices
            # logger.debug(f":emit: <<< {curridx}: {round(total_time, 2)} sec , {round(total_dist/1000,3)} m / {round(total_dist_vtx/1000, 3)} m")
            curridx = curridx + 1


        # Restriction
        # If frequency is high, we have thousands of points.
        # So let's suppose we are close to the managed airport.
        # => We limit high frequency emits to the vicinity of the airport.
        # @todo: It would be better to not generate the emission at the first place...
        # Somehow, the test has to be made somewhere. Let's assume filter() is efficient.
        if RATE_LIMIT is not None and frequency < RATE_LIMIT and EMIT_RANGE is not None:
            if self.move is not None and self.move.airport is not None:
                center = self.move.airport  # yeah, it's a Feature
                before = len(self._emit)
                self._emit = list(filter(lambda f: distance(f, center) < EMIT_RANGE, self._emit))
                logger.debug(f":emit: rate { self.frequency } high, limiting to { EMIT_RANGE }km: before: {before}, after: {len(self._emit)}")
            else:
                logger.warning(f":emit: rate { self.frequency } high, cannot locate airport")

        # transfert common data to each emit point for emission
        # (may be should think about a FeatureCollection-level property to avoid repetition.)
        if len(self.props) > 0:
            p = flatdict.FlatDict(self.props).as_dict()
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
        [l.add(f.getProp(FEATPROP.MARK.value)) for f in self._emit]
        if None in l:
            l.remove(None)
        return l


    def pause(self, sync, duration: float):
        f = findFeatures(self.moves, {FEATPROP.MARK.value: sync})
        if f is not None and len(f) > 0:
            r = f[0]
            s = r.speed()
            if s is not None and s > 0:
                logger.warning(f":pause/serviceTime: speed {s}m/sec at vertex is not 0")
            offset = r.setProp(FEATPROP.PAUSE.value, duration)
            logger.debug(f":pause/serviceTime: found {sync} mark, added {duration} sec. pause")
        # should recompute emit
        if self._emit is not None:  # already computed before...
           self.emit()


    def addToPause(self, sync, duration: float):
        f = findFeatures(self.moves, {FEATPROP.MARK.value: sync})
        if f is not None and len(f) > 0:
            r = f[0]
            s = r.speed()
            if s is not None and s > 0:
                logger.warning(f":pause/serviceTime: speed {s}m/sec at vertex is not 0")
            before = r.getProp(FEATPROP.PAUSE.value) if r.getProp(FEATPROP.PAUSE.value) is not None else 0
            offset = r.setProp(FEATPROP.PAUSE.value, before + duration)
            logger.debug(f":pause/serviceTime: found {sync} mark, added {duration} sec. pause for a total of {r.getProp(FEATPROP.PAUSE.value)}")
        # should recompute emit
        if self._emit is not None:  # already computed before...
           self.emit()


    def serviceTime(self, sync, duration: float):
        self.pause(sync=sync, duration=duration)


    def getRelativeEmissionTime(self, sync: str):
        f = findFeatures(self._emit, {FEATPROP.MARK.value: sync})
        if f is not None and len(f) > 0:
            self.scheduled_emit = []
            r = f[0]
            logger.debug(f":getRelativeEmissionTime: found {sync}")
            offset = r.getProp(FEATPROP.EMIT_REL_TIME.value)
            if offset is not None:
                return offset
            else:
                logger.warning(f":schedule: {FEATPROP.MARK.value} {sync} has no time offset, using 0")
                return 0
        logger.warning(f":getRelativeEmissionTime: {sync} not found in emission")
        return None


    def getAbsoluteEmissionTime(self, sync: str):
        f = findFeatures(self.scheduled_emit, {FEATPROP.MARK.value: sync})
        if f is not None and len(f) > 0:
            logger.debug(f":getAbsoluteEmissionTime: found {sync}")
            return f[0]
        logger.warning(f":getAbsoluteEmissionTime: {sync} not found in emission")
        return None


    def updateEstimatedTime(self):
        """
        Based on this "absolute" time of emission, update "parent" movement ETA/ETD for flights
        and estimated time of service for GSE. In other words, getAbsoluteEmissionTime for estimated
        time events for each type of move.
        """
        ff = None
        source = self.getSource()
        is_arrival = False
        if source is not None:
            if type(source).__name__ in ["Flight", "Arrival", "Departure"]:
                ff = FLIGHT_PHASE.TOUCH_DOWN.value if source.is_arrival() else FLIGHT_PHASE.TAKE_OFF.value
                is_arrival = source.is_arrival()
            elif type(source).__name__.startswith("Service"):
                ff = SERVICE_PHASE.SERVICE_START.value
                is_arrival = source.is_arrival()
            elif type(source).__name__.startswith("Mission"):
                ff = MISSION_PHASE.START.value

            if ff is not None:
                f = self.getAbsoluteEmissionTime(ff)
                if f is not None:
                    esti = datetime.fromtimestamp(f.getAbsoluteEmissionTime())
                    if esti is not None:
                        source.setEstimatedTime(dt=esti)
                        self.addMessage(EstimatedTimeMessage(flight_id=source.getId(),
                                                             is_arrival=is_arrival,
                                                             et=esti))
                    else:
                        logger.warning(":updateEstimatedTime: feature has no absolute emission time")
                else:
                    logger.warning(f":updateEstimatedTime: feature at mark {ff} not found")
            else:
                logger.warning(f":updateEstimatedTime: source {type(source).__name__} has no scheduled time to adjust")
        else:
            logger.warning(":updateEstimatedTime: no source movement to update")


    def schedule(self, sync, moment: datetime):
        """
        Adjust a emission track to synchronize moment at position mkar synch.
        This should only change the EMIT_ABS_TIME property.

        :param      sync:   The synchronize
        :type       sync:   { string }
        :param      moment:  The moment
        :type       moment:  datetime
        """
        offset = self.getRelativeEmissionTime(sync)
        if offset is not None:
            self.offset_name = sync
            self.offset = offset
            logger.debug(f":schedule: {self.offset_name} offset {self.offset} sec")
            when = moment + timedelta(seconds=(- offset))
            logger.debug(f":schedule: emit_point starts at {when} ({when.timestamp()})")
            for e in self._emit:
                p = EmitPoint.new(e)
                t = e.getProp(FEATPROP.EMIT_REL_TIME.value)
                if t is not None:
                    when = moment + timedelta(seconds=(t - offset))
                    p.setProp(FEATPROP.EMIT_ABS_TIME.value, when.timestamp())
                    # logger.debug(f":get: done at {when.timestamp()}")
                self.scheduled_emit.append(p)
            logger.debug(f":schedule: emit_point finishes at {when} ({when.timestamp()}) ({len(self.scheduled_emit)} positions)")
            # now that we have "absolute time", we update the parent
            self.updateEstimatedTime()
            return (True, "Emit::schedule completed")

        return (False, f"Emit::schedule sync {sync} not found")
