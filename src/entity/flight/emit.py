"""
Emit
"""
import os
import json
import logging
from typing import Union

from geojson import FeatureCollection, Point, LineString
from turfpy.measurement import distance, bearing, destination

from ..geo import FeatureWithProps, cleanFeatures, printFeatures

from ..constants import FLIGHT_DATABASE, SLOW_SPEED
from ..parameters import DATA_DIR

logger = logging.getLogger("Emit")


class EmitPoint(FeatureWithProps):
    """
    An EmitPoint is a Feature<Point> with additional information for emission.
    All information to be emited in included into the EmitPoint.
    """
    def __init__(self, geometry: Union[Point, LineString], properties: dict):
        FeatureWithProps.__init__(self, geometry=geometry, properties=properties)
        self._speed = None
        self._vspeed = None


class Emit:
    """
    Emit takes an array of MovePoints to produce a FeatureCollection of decorated features ready for emission.
    """
    def __init__(self, move):
        self.move = move
        self.frequency = 30  # seconds
        self.broadcast = []  # [ EmitPoint ]
        self.props = {}  # general purpose properties added to each emit point

        self.moves = self.move.moves_st


    def save(self):
        """
        Save flight paths to file for emitted positions.
        """
        basename = os.path.join(DATA_DIR, "_DB", FLIGHT_DATABASE, self.move.flight_id)

        filename = os.path.join(basename + "-emit.json")
        with open(filename, "w") as fp:
            json.dump(self.moves, fp, indent=4)

        filename = os.path.join(basename + "-emit.geojson")
        with open(filename, "w") as fp:
            json.dump(FeatureCollection(features=cleanFeatures(self.moves)), fp, indent=4)


    def load(self):
        pass


    def emit(self):

        # Utility subfunctions

        def timediff(c0, idx):  # time it takes to go from c0 to c1
            totald = distance(self.moves[idx], self.moves[idx+1])
            if totald == 0:  # same point...
                logger.warning(":emit:timediff: same point? (%s %s)" % (self.moves[idx], self.moves[idx+1]))
                return 0

            partiald = distance(self.moves[idx], c0)
            portion = partiald / totald

            leftd = totald - partiald  # = distance(c0, self.moves[idx+1])

            v0 = self.moves[idx].speed()
            v1 = self.moves[idx+1].speed()

            v = 0
            if partiald == 0:
                v = self.moves[idx].speed()
            elif leftd == 0:
                v = self.moves[idx+1].speed()
            else:
                v = v0 + portion * (v1 - v0)

            if v < SLOW_SPEED:
                v = SLOW_SPEED

            t = 0
            if (v + v1) != 0:
                t = 2 * leftd / (v + v1)
            else:
                logger.warning(":emit:timediff: v + v1 = 0?")

            r = round(t * 3600000) / 1000
            return r


        def point_on_line(c, n, d):
            brng = bearing(c, n)
            return destination(c, d, brng)


        def destinationOnTrack(c0, duration, idx):  # from c0, moves duration seconds on edges at speed specified at vertices
            totald = distance(self.moves[idx], self.moves[idx+1])

            if totald == 0:  # same point...
                logger.warning(":emit:destinationOnTrack: same point?")

            partiald = distance(self.moves[idx], c0)
            portion = partiald / totald

            v0 = self.moves[idx].speed()
            v1 = self.moves[idx+1].speed()

            v = v0 + portion * (v1 - v0)
            if v < SLOW_SPEED:
                v = SLOW_SPEED

            acc = (v1 * v1 - v0 * v0) / (2 * totald) # a=(u²-v²)/2d
            hourrate = duration / 3600
            dist = v * hourrate + acc * hourrate * hourrate / 2

            nextpos = point_on_line(currpos, self.moves[idx+1], dist)
            return nextpos


        def broadcast(idx, pos, time, reason):
            logger.debug(":broadcast: %s (%d, %f)" % (reason, idx, time))
            e = EmitPoint(geometry=pos["geometry"], properties=pos["properties"])
            e.setProp("broadcast_time", time)
            self.broadcast.append(pos)


        # collect common props from flight
        # collect common props from aircraft

        # build emission points
        total_time = 0
        curridx = 0
        currpos = self.moves[curridx]

        # Add first point
        broadcast(curridx, currpos, total_time, "start")

        time_to_next_emit = self.frequency  # we could actually random from (0..self.frequency) to randomly start broadcast
        while curridx < (len(self.moves) - 1):
            next_vtx = self.moves[curridx + 1]
            time_to_next_vtx = timediff(currpos, curridx)
            logger.debug(":emit: %f: to next vertex" % (time_to_next_vtx))

            if (time_to_next_emit > 0) and (time_to_next_emit < self.frequency) and (time_to_next_vtx > time_to_next_emit):   # If next vertex far away, we move during to_next_emit on edge and emit

                total_time = total_time + time_to_next_vtx
                logger.debug("moving from vertex with time remaining.. (%d, %s, %f, %f)" % (curridx, next_vtx, time_to_next_emit, time_to_next_vtx))  # if we are here, we know we will not reach the next vertex
                broadcast(curridx, currpos, total_time, "moving on edge with time remaining to next vertex")
                currpos = next_vtx
                time_to_next_emit = time_to_next_emit - time_to_next_vtx  # time left before next emit
                logger.debug("..done moving to next vertex with time left. %f sec left before next emit, moving to next vertex" % (time_to_next_emit))

            else:

                while time_to_next_vtx > self.frequency:

                    logger.debug("moving on edge.. %f, %f" % (time_to_next_vtx, self.frequency))
                    total_time = total_time + self.frequency
                    nextpos = destinationOnTrack(currpos, self.frequency, curridx)
                    broadcast(curridx, currpos, total_time, "en route on vertex %d" % curridx)
                    currpos = nextpos
                    time_to_next_vtx = timediff(currpos, curridx)

                logger.debug(".. done moving on edge. %f remaining" % (time_to_next_vtx))
                if time_to_next_vtx > 0:  # jump to next vertex

                    d0 = distance(currpos, next_vtx)
                    logger.debug("jumping to next vertex.. (%s, %f km, %f sec)" % (next_vtx, d0, time_to_next_vtx))
                    total_time = total_time + time_to_next_vtx
                    broadcast(curridx, currpos, total_time, "at vertex" if curridx < (len(self.moves)-2) else "at last vertex")
                    currpos = next_vtx
                    to_next_emit = self.frequency - time_to_next_vtx  # time left before next emit
                    logger.debug(".. done jumping to next vertex. %f sec left before next emit" % (to_next_emit))

            curridx = curridx + 1

        # transfert common data to each emit point for emission
        # (may be should think about a FeatureCollection-level property to avoid repetition.)
        if len(self.props) > 0:
            for f in self.broadcast:
                f.addProps(self.props)

        printFeatures(self.broadcast, "broadcast")
        return (True, "Emit::emit completed")


    def get(self, synch, moment):
        return None
