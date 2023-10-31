import logging
import os
import json
from emitpy.geo import FeatureWithProps
from turf import FeatureCollection

logger = logging.getLogger("aoi")


class AreasOfInterest(FeatureCollection):
    def __init__(self, name, filename):
        FeatureCollection.__init__(self, features=[])
        self.name = name
        self.filename = filename
        self.init()

    def init(self):
        filename = self.filename
        with open(filename, "r") as file:
            data = json.load(file)
            self.features = [FeatureWithProps.new(f) for f in data["features"]]
