"""
A succession of positions where a vehicle passes.
"""
import os
import io
import json
import logging
import copy

from datetime import datetime, timedelta

from geojson import Point, FeatureCollection, Feature

from tabulate import tabulate

from emitpy.geo import FeatureWithProps, cleanFeatures, findFeatures, asLineString, get_bounding_box
from emitpy.constants import MOVES_DATABASE, FEATPROP
from emitpy.parameters import MANAGED_AIRPORT_AODB
from emitpy.message import Messages

logger = logging.getLogger("Movement")


class MovePoint(FeatureWithProps):
    """
    A MovePoint is an application waypoint through which vehicle passes.
    It is a GeoJSON Feature<Point> with facilities to set a few standard
    properties like altitude, speed, vertical speed and properties.
    It can also set colors for geojson.io map display.
    Altitude is stored in third geometry coordinates array value.
    """
    def __init__(self, geometry: Point, properties: dict):
        FeatureWithProps.__init__(self, geometry=geometry, properties=copy.deepcopy(properties))

    def getRelativeEmissionTime(self):
        t = self.getProp(FEATPROP.EMIT_REL_TIME.value)
        return t if t is not None else 0

    def getAbsoluteEmissionTime(self):
        t = self.getProp(FEATPROP.EMIT_ABS_TIME.value)
        return t if t is not None else 0


class Movement(Messages):

    def __init__(self, airport: "ManagedAirportBase", reason: "Messages"):
        Messages.__init__(self)

        self.reason = reason    # Core entity of the movement: Flight or ground service.
        self.airport = airport
        self._points = []  # Array of Features<Point>

        # Movement scheduling
        self._scheduled_points = []
        self.version = 0
        self.offset_name = None
        self.offset = None

        # self.reason.setMovement(movement=self)

    def getId(self):
        return self.reason.getId()

    def saveFile(self):
        """
        Save flight paths to 3 files for flight plan, detailed movement, and taxi path.
        Save a technical json file which can be loaded later, and GeoJSON files for display.
        @todo should save file format version number.
        """
        ident = self.getId()
        basename = os.path.join(MANAGED_AIRPORT_AODB, MOVES_DATABASE, ident)

        def saveMe(arr, name):
            # filename = os.path.join(basename + "-" + name + ".json")
            # with open(filename, "w") as fp:
            #     json.dump(arr, fp, indent=4)

            filename = os.path.join(basename + "-" + name + ".geojson")
            with open(filename, "w") as fp:
                json.dump(FeatureCollection(features=cleanFeatures(arr)), fp, indent=4)

        # saveMe(self.getMovePoints(), "moves")
        ls = Feature(geometry=asLineString(self.getMovePoints()))
        saveMe(self.getMovePoints() + [ls], "moves_ls")

        logger.debug(f"saved {ident}")
        return (True, "Movement::save saved")

    def load(self, ident):
        """
        Load flight paths from 3 files for flight plan, detailed movement, and taxi path.
        File must be saved by above saveFile() function.
        """
        basename = os.path.join(MANAGED_AIRPORT_AODB, MOVES_DATABASE, ident)

        filename = os.path.join(basename, "-moves.json")
        with open(filename, "r") as fp:
            self._points = json.load(fp)

        logger.debug("loaded %d " % ident)
        return (True, "Movement::load loaded")

    def getInfo(self):
        # Drill down on original object to get info
        return {
            "type": "abstract"
        }

    def getPoints(self):
        return self._points

    def getMovePoints(self):
        logger.debug(f"getting {len(self._points)} base positions ({type(self).__name__})")
        return self._points

    def setMovePoints(self, move_points):
        self._points = move_points

    def getScheduledPoints(self):
        return self._scheduled_points

    def getMessages(self):
        m = super().getMessages()
        # logger.debug(f"added super()")
        s = self.getSource()
        if s is not None:
            m = m + s.getMessages()
            # logger.debug(f"added source")
        return m

    def getSource(self):
        # Abstract
        return None

    def is_event_service(self):
        svc = self.getSource()
        if svc is not None and type(svc).__name__ == "EventService":  # isinstance(svc, EventService)
            return True
        return False

    def move(self):
        """
        Perform actual movement
        """
        return (False, "Movement::move done")

    def interpolate(self):
        """
        Compute interpolated values for different attributes based on distance.
        This is a simple linear interpolation based on distance between points.
        """
        return (True, "Movement::interpolated speed and altitude")

    def time(self):
        """
        Time 0 is start of roll for takeoff (Departure) or takeoff from origin airport (Arrival).
        Last time is touch down at destination (Departure) or end of roll out (Arrival).
        """
        return (True, "Movement::time computed")


    def resetDelays(self):
        """
        Removes all waiting time in movement, included service times.
        """
        for f in self.getMovePoints():
            before = f.pause(-1)
            if before > 0:
                n = f.getProp(FEATPROP.MARK.value)
                logger.debug(f"removed delay at {n} ({before} secs.)")
                f.setPause(0)


    def addDelays(self, delays: dict):
        """
        Adds pauses. delays is a dictionary with {"_mark_name": delay_in_seconds} entries.
        _mark that are not found are reported so and ignored.

        :param      delays:  The delays
        :type       delays:  dict
        """
        for name, duration in delays.items():
            farr = findFeatures(self.getMovePoints(), {FEATPROP.MARK.value: name})
            if len(farr) == 0:
                logger.warning(f"feature mark {name} not found")
                return
            ## assume at most one...
            f = farr[0]
            f.setAddToPause(duration)


    def getMarkList(self):
        """
        List all movement marks.

        :returns:   { array of movement marks }
        :rtype:     { ( str ) }
        """
        # l = set()
        # [l.add(f.getProp(FEATPROP.MARK.value)) for f in self.getMovePoints()]
        # if None in l:
        #     l.remove(None)
        # return l
        marks = []
        for f in self.getMovePoints():
            marks.append(f.getProp(FEATPROP.MARK.value))
        marks = set(marks)
        if None in marks:
             marks.remove(None)
        return marks


    def listPauses(self):
        """
        List all movement marks that have a pause.

        :returns:   { array of movement marks }
        :rtype:     { ( str ) }
        """
        marks = []
        for f in self.getMovePoints():
            if f.pause(-1) > 0:
                marks.append(f.getProp(FEATPROP.MARK.value))
        return set(marks)


    def getBoundingBox(self, rounding: float = None):
        """
        get bounding box of whole movement.
        assumes  90 (north) <= lat <= -90 (south), and -180 (west) < lon < 180 (east)
        """
        bb = get_bounding_box(self.getMovePoints(), rounding)
        logger.debug(f"bounding box: {bb}")
        return bb


    def getMarkList(self):
        l = set()
        [l.add(f.getMark()) for f in self.getPoints()]
        if None in l:
            l.remove(None)
        return l


    def getRelativeEmissionTime(self, sync: str):
        if self.is_event_service():
            label = self.getSource().label
            logger.debug(f"event service {label} relative time is relative to on/off block (was {sync}).")
            return 0  # sync info in message at creation

        f = findFeatures(self.getPoints(), {FEATPROP.MARK.value: sync})
        if f is not None and len(f) > 0:
            r = f[0]
            logger.debug(f"found {sync}")
            offset = r.getProp(FEATPROP.EMIT_REL_TIME.value)
            if offset is not None:
                return offset
            else:
                logger.warning(f"{FEATPROP.MARK.value} {sync} has no time offset, using 0")
                return 0
        logger.warning(f"{self.getId()}: {sync} not found in ({self.getMarkList()})")
        return None


    def schedule(self, sync, moment: datetime, do_print: bool = False):
        """
        """
        if self.is_event_service():
            return (True, "Movement::schedule: no need to save event service")

        # logger.debug(f"mark list: {self.getMarkList()}")
        offset = self.getRelativeEmissionTime(sync)
        if offset is not None:
            offset = int(offset)  # pylint E1130
            self.offset_name = sync
            self.offset = offset
            logger.debug(f"{self.offset_name} offset {self.offset} sec")
            when = moment + timedelta(seconds=(- offset))
            logger.debug(f"point starts at {when} ({when.timestamp()})")
            self._scheduled_points = []  # brand new scheduling, reset previous one
            for e in self.getPoints():
                p = MovePoint.new(e)
                t = e.getProp(FEATPROP.EMIT_REL_TIME.value)
                if t is not None:
                    when = moment + timedelta(seconds=(t - offset))
                    p.setProp(FEATPROP.EMIT_ABS_TIME.value, when.timestamp())
                    p.setProp(FEATPROP.EMIT_ABS_TIME_FMT.value, when.isoformat())
                    # logger.debug(f"done at {when.timestamp()}")
                self._scheduled_points.append(p)
            logger.debug(f"point finishes at {when} ({when.timestamp()}) ({len(self._scheduled_points)} positions)")
            # now that we have "absolute time", we update the parent
            if do_print:
                dummy = self.getTimedMarkList()
            return (True, "Movement::schedule completed")

        logger.warning(f"{sync} mark not found")
        return (False, f"Movement::schedule {sync} mark not found")


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
                    t = round(f.getProp(FEATPROP.EMIT_REL_TIME.value),  1)
                line = []
                line.append(m)
                line.append(l[m]["rel"])
                line.append(datetime.fromtimestamp(l[m]["ts"]).astimezone().replace(microsecond = 0))
                table.append(line)
                # logger.debug(f"{m.rjust(25)}: t={t:>7.1f}: {f.getProp(FEATPROP.EMIT_ABS_TIME_FMT.value)}")

        table = sorted(table, key=lambda x: x[2])  # absolute emission time
        print(tabulate(table, headers=MARK_LIST), file=output)

        contents = output.getvalue()
        output.close()
        logger.debug(f"{contents}")

        return l


