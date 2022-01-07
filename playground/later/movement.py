"""
A Movement is a transport from a Departure location to an Arrival location.
A Movement has a scheduled date/time.
A Movement is managed by an Operator.
"""
from location import Location
from operator import Operator


FLIGHT_PHASE = [
    "UNKNOWN",
    "TAXI",
    "TAKE_OFF",
    "TO_ROLL",
    "ROTATE",
    "LIFT_OFF",
    "INITIAL_CLIMB",
    "CLIMB",
    "CRUISE",
    "DESCEND",
    "APPROACH",
    "FINAL",
    "LANDING",
    "FLARE",
    "TOUCH_DOWN",
    "ROLL_OUT",
    "STOPPED_ON_RWY"
]


class Movement:

    def __init__(self, name: str, scheduled: str, departure: Location, arrival: Location, operator: Operator):
        self.name = name
        self.departure = departure
        self.arrival = arrival
        self.scheduled = scheduled
        self.operator = operator
