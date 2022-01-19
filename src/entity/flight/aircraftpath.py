"""
A succession of positions where the aircraft passes.
"""
from geojson import Feature
from ..flight import Flight


class PathPoint(Feature):
    """
    A path point is a Feature with a Point geometry and mandatory properties for movements speed and altitude.
    """
    def __init__(self, lat: float, lon: float, alt: float = None, speed: float = 0):
        Feature.__init__(self, geometry=Point((lon, lat, alt)), properties={SPEED: speed})


class AircraftPath:
    """
    Flightpath build the detailed path of the flight.
    """

    def __init__(self, flight: Flight):
        self.flight = flight
        self.route = None

    def vnav(self):
        """
        Perform vertical navigation for route
        """
        pass


    def speeds(self):
        """
        Perform speed calculation, control, and adjustments for route
        """
        pass