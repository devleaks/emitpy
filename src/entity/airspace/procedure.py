"""
A Turnaround is a collection of Services to be performed on an aircraft during a turn-around.

"""
from .xpairspace import Waypoint


class FixAlt:
    """
    A FixAlt is a Fix with minimum and/or maximum altitude constraints
    """
    def __init__(self, waypoint: Waypoint, alt_min: float = None, alt_max: float = None):
        self.alt_min = alt_min
        self.alt_max = alt_max


class FlightRoute:
    """
    A FlightRoute is an array of FixAlt
    """
    def __init__(self, name: str, route: [FixAlt]):
        self.name = name
        self.route = route


class SID(FlightRoute):
    """
    A Standard Instrument Departure is a special instance of a FlightRoute.
    """
    def __init__(self, name: str, route: [FixAlt]):
        FlightRoute.__init__(self, name, route)


class STAR(FlightRoute):
    """
    A Standard Terminal Arrival Route is a special instance of a FlightRoute.
    """
    def __init__(self, name: str, route: [FixAlt]):
        FlightRoute.__init__(self, name, route)
        self.name = name


class Hold:
    """
    A Holding position.
    """
    def __init__(self, waypoint: Waypoint, course: float, turn: str, alt_min: int = None, alt_max: int = None, leg_time: float = 60):
        self.course = course
        self.turn = turn
        self.alt_min = alt_min
        self.alt_max = alt_max
        self.leg_time = leg_time
