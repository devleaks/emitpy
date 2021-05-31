from datetime import datetime, timedelta
import logging
logger = logging.getLogger("Flight")

from .airport import Airport
from .airline import Airline
from .aircraft import Aircraft
from .info import Info
from .airport import Parking

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


class Flight(Info):

    def __init__(self, name: str, scheduled: str, departure: Airport, arrival: Airport, operator: Airline, aircraft: Aircraft, gate: Parking):
        Info.__init__(self)
        self.name = name
        self.apt_departure = departure
        self.apt_arrival = arrival
        self.scheduled = scheduled
        self.operator = operator
        self.aircraft = aircraft
        self.gate = gate
        self.codeshare = None
        logger.debug(self)

    @staticmethod
    def roundTime(dt: datetime, roundTo: int = 300):
       """Round a datetime object to any time lapse in seconds
       dt : datetime.datetime object, default now.
       roundTo : Closest number of seconds to round to, default 5 minutes.
       Author: Thierry Husson 2012 - Use it as you want but don't blame me.
       """
       if dt == None: dt = datetime.now()
       seconds = (dt.replace(tzinfo=None) - dt.min).seconds
       rounding = (seconds + roundTo / 2) // roundTo * roundTo
       return dt + timedelta(0, rounding-seconds, -dt.microsecond)

    def __str__(self):
        return "%s %s: %s>%s %s gate %s (%s %s)" % (self.operator.orgId, self.name, self.apt_departure.icao, self.apt_arrival.icao,
               Flight.roundTime(self.scheduled), self.gate, self.aircraft.aircraft_type.icao, self.aircraft.name)



    def departure(self, apt: Airport):
        return self.apt_departure == apt


    def arrival(self, apt: Airport):
        return self.apt_arrival == apt
