"""
Emit
"""
from ..flight import Flight


class FlightPath:
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
