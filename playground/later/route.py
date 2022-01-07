from airport import Airport


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


class Route:

    def __init__(self, name: str, scheduled: str, departure: Airport, arrival: Airport):
        self.name = name
        self.departure = departure
        self.arrival = arrival

