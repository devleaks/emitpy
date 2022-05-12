"""
A succession of positions where a vehicle passes.
"""
import os
import json
import logging
from typing import Union
import copy

from geojson import Point, LineString, FeatureCollection, Feature

from emitpy.geo import FeatureWithProps, cleanFeatures, printFeatures, findFeatures, asLineString
from emitpy.constants import FLIGHT_DATABASE, FEATPROP
from emitpy.parameters import AODB_DIR
from emitpy.utils import Messages

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


class Movement(Messages):

    def __init__(self, airport: "AirportBase"):
        self.airport = airport
        self.moves = []  # Array of Features<Point>
        self.messages = []  # Array of Messages

    def getId(self):
        return "Movement::abstract-class-id"

    def save(self):
        """
        Save flight paths to 3 files for flight plan, detailed movement, and taxi path.
        Save a technical json file which can be loaded later, and GeoJSON files for display.
        @todo should save file format version number.
        """
        ident = self.getId()
        basename = os.path.join(AODB_DIR, FLIGHT_DATABASE, ident)

        def saveMe(arr, name):
            # filename = os.path.join(basename + "-" + name + ".json")
            # with open(filename, "w") as fp:
            #     json.dump(arr, fp, indent=4)

            filename = os.path.join(basename + "-" + name + ".geojson")
            with open(filename, "w") as fp:
                json.dump(FeatureCollection(features=cleanFeatures(arr)), fp, indent=4)

        # saveMe(self.moves, "moves")
        ls = Feature(geometry=asLineString(self.moves))
        saveMe(self.moves + [ls], "moves_ls")

        logger.debug(f":save: saved {ident}")
        return (True, "Movement::save saved")

    def load(self, ident):
        """
        Load flight paths from 3 files for flight plan, detailed movement, and taxi path.
        File must be saved by above save() function.
        """
        basename = os.path.join(AODB_DIR, FLIGHT_DATABASE, ident)

        filename = os.path.join(basename, "-moves.json")
        with open(filename, "r") as fp:
            self.moves = json.load(fp)

        logger.debug(":load: loaded %d " % ident)
        return (True, "Movement::load loaded")

    def getInfo(self):
        # Drill down on original object to get info
        return {
            "type": "abstract"
        }

    def getMoves(self):
        return self.moves

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

    def addDelay(self, name: str, seconds: int):
        farr = findFeatures(self.moves, {FEATPROP.MARK.value: name})
        if len(farr) == 0:
            logger.warning(f":addDelay: feature mark {name} not found")
            return
        ## assume at most one...
        f = farr[0]
        f.setProp(FEATPROP.DELAY.value, seconds)
