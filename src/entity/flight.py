import logging
logger = logging.getLogger("Flight")

from .airport import Airport
from .airline import Airline
from .aircraft import Aircraft
from .parking import Parking

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


class Flight:

    def __init__(self, name: str, scheduled: str, departure: Airport, arrival: Airport, operator: Airline, aircraft: Aircraft, gate: Parking):
        self.name = name
        self.apt_departure = departure
        self.apt_arrival = arrival
        self.scheduled = scheduled
        self.operator = operator
        self.aircraft = aircraft
        self.gate = gate
        self.codeshare = None
        logger.debug("init: %s from %s to %s by %s on %s at %s gate %s", self.name, self.apt_departure.icao, self.apt_arrival.icao, self.operator.orgId,
            self.aircraft.name, self.scheduled, self.gate)


    def departure(self, apt: Airport):
        return self.apt_departure == apt


    def arrival(self, apt: Airport):
        return self.apt_arrival == apt
