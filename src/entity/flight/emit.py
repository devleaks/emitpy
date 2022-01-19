"""
Emit
"""
import os
import json
from geojson import Feature, LineString, Point, FeatureCollection
from ..constants import FOOT


class Emit:
    """
    Emit takes a  FeatureCollection of decorated Feaures to produce a FeatureCollection of decorated features ready for emission.
    """

    def __init__(self, src: FeatureCollection):
        self.src = src


    def emit(self):
        pass
