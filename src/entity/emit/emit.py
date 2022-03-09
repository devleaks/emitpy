"""
Emit
"""
import os
import json
import logging
from datetime import datetime, timedelta
from random import randrange

from geojson import FeatureCollection, Point, LineString
from geojson.geometry import Geometry
from turfpy.measurement import distance, bearing, destination

from ..geo import FeatureWithProps, cleanFeatures, printFeatures, findFeatures, Movement

from ..constants import FLIGHT_DATABASE, SLOW_SPEED, FEATPROP
from ..parameters import AODB_DIR

logger = logging.getLogger("Emit")


class EmitPoint(FeatureWithProps):
    """
    An EmitPoint is a Feature<Point> with additional information for emission.
    All information to be emited in included into the EmitPoint.
    """
    def __init__(self, geometry: Geometry, properties: dict):
        FeatureWithProps.__init__(self, geometry=geometry, properties=properties)

    def getBroadcastTime(self):
        t = self.getProp("broadcast_absolute_time")
        return t if t is not None else 0


class Emit:
    """
    Emit takes an array of MovePoints to produce a FeatureCollection of decorated features ready for emission.
    """
    def __init__(self, move: Movement = None):
        self.move = move
        self.moves = None
        self.frequency = 30  # seconds
        self._emit = []  # [ EmitPoint ]
        self.broadcast = []  # [ EmitPoint ]
        self.props = {}  # general purpose properties added to each emit point

        if move is not None:
            self.moves = self.move.getMoves()


    def save(self):
        """
        Save flight paths to file for emitted positions.
        """
        ident = self.move.getId()
        basename = os.path.join(AODB_DIR, FLIGHT_DATABASE, ident)

        # filename = os.path.join(basename + "-5-emit.json")
        # with open(filename, "w") as fp:
        #     json.dump(self._emit, fp, indent=4)
        filename = os.path.join(basename + "-5-emit.geojson")
        with open(filename, "w") as fp:
            json.dump(FeatureCollection(features=cleanFeatures(self._emit)), fp, indent=4)

        logger.debug(":save: saved %s" % ident)

    def load(self, flight_id):
        # load output of Movement file.
        basename = os.path.join(AODB_DIR, FLIGHT_DATABASE, flight_id)

        filename = os.path.join(basename, "-4-move.json")
        if os.path.exists(filename):
            with open(filename, "r") as fp:
                self.moves = json.load(fp)
            logger.debug(":loadAll: loaded %d " % self.flight_id)
            return (True, "Movement::load loaded")

        logger.debug(":loadAll: cannot find %s" % filename)
        return (False, "Movement::load not loaded")


        pass


    def emit(self, frequency: int = 30):
        # Utility subfunctions
        def point_on_line(c, n, d):
            # brng = bearing(c, n)
            # dest = destination(c, d / 1000, brng, {"units": "km"})
            return FeatureWithProps.convert(destination(c, d / 1000, bearing(c, n), {"units": "km"}))

        def time_distance_to_next_vtx(c0, idx):  # time it takes to go from c0 to vtx[idx+1]
            totald = distance(self.moves[idx], self.moves[idx+1]) * 1000  # km
            if totald == 0:  # same point...
                # logger.warning(":emit:time_distance_to_next_vtx: same point? (%s %s)" % (self.moves[idx], self.moves[idx+1]))
                return 0
            partiald = distance(self.moves[idx], c0) * 1000  # km
            portion = partiald / totald
            leftd = totald - partiald  # = distance(c0, self.moves[idx+1])
            v0 = self.moves[idx].speed()
            v1 = self.moves[idx+1].speed()
            v = v0 + portion * (v1 - v0)
            v = max(v, SLOW_SPEED)

            t = 0
            if (v + v1) != 0:
                t = 2 * leftd / (v + v1)
            else:
                logger.warning(":emit:time_distance_to_next_vtx: v + v1 = 0?")

            # logger.debug(":time_distance_to_next_vtx: (%d, tot=%f, done=%f, v=%f, v0=%f, v1=%f, t=%f)" % (idx, totald, partiald, v, v0, v1, t))
            return t

        def destinationOnTrack(c0, duration, idx):  # from c0, moves duration seconds on edges at speed specified at vertices
            totald = distance(self.moves[idx], self.moves[idx+1]) * 1000  # km
            if totald == 0:  # same point...
                logger.warning(":emit:destinationOnTrack: same point?")
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

        def broadcast(idx, pos, time, reason, waypt=False):
            e = EmitPoint(geometry=pos["geometry"], properties=pos["properties"])
            e.setProp(FEATPROP.BROADCAST_REL_TIME.value, time)
            e.setProp(FEATPROP.BROADCAST_INDEX.value, len(self._emit))
            e.setProp(FEATPROP.BROADCAST.value, not waypt)
            if waypt:
                e.setColor("#eeeeee")
                #logger.debug(":broadcast: %s (%s)" % (reason, timedelta(seconds=time)))
            else:
                e.setColor("#ccccff")
                #logger.debug(":broadcast: %s (%d, %f (%s))" % (reason, idx, time, timedelta(seconds=time)))
            self._emit.append(e)

        # collect common props from flight
        # if self.move.flight:
        #   props = props + self.move.flight.getEmitData()
        # collect common props from aircraft
        # if self.move.flight.aircraft:  # may be added by above function?
        #   props = props + self.move.flight.aircraft.getEmitData()
        # alt, speed, and vspeed info will be added here.

        self.frequency = frequency

        # build emission points
        total_dist = 0   # sum of distances between emissions
        total_dist_vtx = 0  # sum of distances between vertices
        total_time = 0   # sum of times between emissions

        curridx = 0
        currpos = self.moves[curridx]

        # Add first point
        broadcast(curridx, currpos, total_time, "start")

        time_to_next_emit = randrange(self.frequency)  # we could actually random from (0..self.frequency) to randomly start broadcast

        future_emit = self.frequency
        # future_emit = self.frequency - 0.2 * self.frequency + randrange(0.4 * self.frequency)  # random time between emission DANGEROUS!

        while curridx < (len(self.moves) - 1):
            # We progress one leg at a time, leg is from idx -> idx+1.
            next_vtx = self.moves[curridx + 1]
            time_to_next_vtx = time_distance_to_next_vtx(currpos, curridx)
            # logger.debug(":emit: >>>> %d: %f sec to next emit, %f sec to next vertex" % (curridx, time_to_next_emit, time_to_next_vtx))
            ## logger.debug(":emit: START: %d: %f sec to next emit, %f sec to next vertex" % (curridx, time_to_next_emit, time_to_next_vtx))

            if (time_to_next_emit > 0) and (time_to_next_emit < future_emit) and (time_to_next_emit < time_to_next_vtx):
                # We need to emit before next vertex
                # logger.debug("moving on edge with time remaining to next emit.. (%d, %f, %f)" % (curridx, time_to_next_emit, time_to_next_vtx))  # if we are here, we know we will not reach the next vertex
                ## logger.debug(":emit: EBEFV: %d: %f sec to next emit, %f sec to next vertex" % (curridx, time_to_next_emit, time_to_next_vtx))
                newpos = destinationOnTrack(currpos, time_to_next_emit, curridx)
                total_time = total_time + time_to_next_emit
                controld = distance(currpos, newpos) * 1000  # km
                total_dist = total_dist + controld
                broadcast(curridx, newpos, total_time, "moving on edge with time remaining to next emit")
                currpos = newpos
                time_to_next_emit = future_emit
                time_to_next_vtx = time_distance_to_next_vtx(currpos, curridx)
                # logger.debug("..done moving on edge with time remaining to next emit. %f sec left before next emit, %f to next vertex" % (time_to_next_emit, time_to_next_vtx))

            if (time_to_next_emit > 0) and (time_to_next_emit < future_emit) and (time_to_next_vtx < time_to_next_emit):
                ##logger.debug(":emit: RVBFE: %d: %f sec to next emit, %f sec to next vertex" % (curridx, time_to_next_emit, time_to_next_vtx))
                # We will reach next vertex before we need to emit
                # logger.debug("moving from to vertex with time remaining before next emit.. (%d, %f, %f)" % (curridx, time_to_next_emit, time_to_next_vtx))  # if we are here, we know we will not reach the next vertex
                total_time = total_time + time_to_next_vtx
                controld = distance(currpos, next_vtx) * 1000  # km
                total_dist = total_dist + controld
                broadcast(curridx, next_vtx, total_time, f"at vertex { curridx + 1 }", True)  # ONLY IF BROADCAST AT VERTEX
                currpos = next_vtx
                time_to_next_emit = time_to_next_emit - time_to_next_vtx  # time left before next emit
                # logger.debug("..done moving to next vertex with time remaining before next emit. %f sec left before next emit, moving to next vertex" % (time_to_next_emit))

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
                    broadcast(curridx, currpos, total_time, f"en route after vertex {curridx}")
                    currpos = nextpos
                    time_to_next_vtx = time_distance_to_next_vtx(currpos, curridx)
                    time_to_next_emit = future_emit

                #logger.debug(".. done moving on edge by %f sec. %f remaining to next vertex" % (time_to_next_emit, time_to_next_vtx))

                if time_to_next_vtx > 0:
                    # jump to next vertex because time_to_next_vtx <= future_emit
                    ## logger.debug(":emit: TONXV: %d: %f sec to next emit, %f sec to next vertex" % (curridx, time_to_next_emit, time_to_next_vtx))
                    controld = distance(currpos, next_vtx) * 1000  # km
                    # logger.debug("jumping to next vertex.. (%f m, %f sec)" % (controld, time_to_next_vtx))
                    total_time = total_time + time_to_next_vtx
                    controld = distance(currpos, next_vtx) * 1000  # km
                    total_dist = total_dist + controld
                    broadcast(curridx, next_vtx, total_time, f"at vertex { curridx + 1 }", True)  # ONLY IF BROADCAST AT VERTEX
                    currpos = next_vtx
                    time_to_next_emit = time_to_next_emit - time_to_next_vtx  # time left before next emit
                    # logger.debug(".. done jumping to next vertex. %f sec left before next emit" % (time_to_next_emit))

            controld = distance(self.moves[curridx], next_vtx) * 1000  # km
            total_dist_vtx = total_dist_vtx + controld  # sum of distances between vertices
            #logger.debug(":emit: END> %d: %f sec , %f m / %f m" % (curridx, round(total_time, 2), round(total_dist/1000,3), round(total_dist_vtx/1000, 3)))
            curridx = curridx + 1

        # transfert common data to each emit point for emission
        # (may be should think about a FeatureCollection-level property to avoid repetition.)
        if len(self.props) > 0:
            for f in self._emit:
                f.addProps(self.props)

        # logger.debug(":emit: summary: %f vs %f sec, %f vs %f km, %d vs %d" % (round(total_time, 2), round(self.moves[-1].time(), 2), round(total_dist/1000, 3), round(total_dist_vtx/1000, 3), len(self.moves), len(self._emit)))
        # logger.debug(":emit: summary: %s vs %s, %f vs %f km, %d vs %d" % (timedelta(seconds=total_time), timedelta(seconds=round(self.moves[-1].time(), 2)), round(total_dist/1000, 3), round(total_dist_vtx/1000, 3), len(self.moves), len(self._emit)))
        logger.debug(":emit: summary: %s vs %s, %f vs %f km, %d vs %d" % (timedelta(seconds=total_time), timedelta(seconds=self.moves[-1].time()), round(total_dist/1000, 3), round(total_dist_vtx/1000, 3), len(self.moves), len(self._emit)))

        printFeatures(self._emit, "broadcast")
        return (True, "Emit::emit completed")


    def getMarkList(self):
        l = set()
        [l.add(f.getProp(FEATPROP.MARK.value)) for f in self._emit]
        if None in l:
            l.remove(None)
        return l

    def schedule(self, sync, moment: datetime):
        """
        Adjust a emission track to synchronize moment at position mkar synch.

        :param      sync:   The synchronize
        :type       sync:   { string }
        :param      moment:  The moment
        :type       moment:  datetime
        """
        f = findFeatures(self._emit, {FEATPROP.MARK.value: sync})
        if f is not None and len(f) > 0:
            self.broadcast = []
            r = f[0]
            logger.debug(f":get: found {sync} mark at {moment}")
            offset = r.getProp("broadcast_relative_time")
            if offset is not None:
                logger.debug(f":get: {sync} offset {offset} sec")
                when = moment + timedelta(seconds=(- offset))
                logger.debug(f":get: broadcast starts at {when}")
                for e in self._emit:
                    p = EmitPoint(geometry=e["geometry"], properties=e["properties"])
                    t = e.getProp(FEATPROP.BROADCAST_REL_TIME.value)
                    if t is not None:
                        when = moment + timedelta(seconds=(t - offset))
                        p.setProp(FEATPROP.BROADCAST_ABS_TIME.value, when.timestamp())
                        # logger.debug(f":get: done at {when.timestamp()}")
                    self.broadcast.append(p)
                logger.debug(f":get: broadcast finishes at {when} ({len(self.broadcast)} positions)")
            else:
                logger.warning(f":get: {FEATPROP.MARK.value} {sync} has no time offset")
        else:
            logger.warning(f":get: {FEATPROP.MARK.value} {sync} not found")

        return None
