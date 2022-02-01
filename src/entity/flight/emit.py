"""
Emit
"""
from geojson import Feature, LineString, Point, FeatureCollection


class EmitPoint(Feature):
    pass

class Emit:
    """
    Emit takes a  FeatureCollection of decorated Feaures to produce a FeatureCollection of decorated features ready for emission.
    """

    def __init__(self, src: FeatureCollection):
        self.src = src


    def emit(self):
        pass
