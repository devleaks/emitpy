"""
A succession of positions where a vehicle passes.
"""
import os
import json
import logging
from typing import Union
import copy

from geojson import Point, LineString, FeatureCollection, Feature

from emitpy.geo import FeatureWithProps, cleanFeatures, findFeatures, asLineString
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


class Movement(Messages):

    def __init__(self, airport: "ManagedAirportBase"):
        Messages.__init__(self)

        self.airport = airport
        self._move_points = []  # Array of Features<Point>

    def getId(self):
        return "Movement::abstract-class-id"

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
            self._move_points = json.load(fp)

        logger.debug("loaded %d " % ident)
        return (True, "Movement::load loaded")

    def getInfo(self):
        # Drill down on original object to get info
        return {
            "type": "abstract"
        }

    def getMovePoints(self):
        return self._move_points

    def setMovePoints(self, move_points):
        self._move_points = move_points

    def getMessages(self):
        m = super().getMessages()
        logger.debug(f"added super()")
        s = self.getSource()
        if s is not None:
            m = m + s.getMessages()
            logger.debug(f"added source")
        return m

    def getSource(self):
        # Abstract
        return None

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
