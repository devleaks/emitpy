"""
Point
"""
from geojson import Point
from ..constants import SPEED


class RoutePoint(Feature):
    """
    A route point is a Feature with a Point geometry and mandatory properties for movements speed and altitude.
    """

    def __init__(self, lat: float, lon: float, alt: float = None, speed: float = 0):
        Feature.__init__(self, geometry=Point((lon, lat, alt)), properties={SPEED: speed})

