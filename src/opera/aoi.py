import logging
import os
import json
from emitpy.geo import FeatureWithProps
from turf import FeatureCollection

logger = logging.getLogger("aoi")


class AreasOfInterest(FeatureCollection):
    """Areas of Interest is collection of polygons on the ground of the airport.

    The collection of polygon is named.

    """

    def __init__(self, name, filename):
        """Creates an AreasOfInterest

        Args:
            name ([str]): Name of collection
            filename ([str]): Filename of collection. Should normally be a geojson FeatureCollection.
        """
        FeatureCollection.__init__(self, features=[])
        self.name = name
        self.filename = filename
        self.init()

    def init(self):
        """Initialize an AreasOfInterest

        Load polygon features from file.
        """
        filename = self.filename
        with open(filename, "r") as file:
            data = json.load(file)
            self.features = [FeatureWithProps.new(f) for f in data["features"]]
