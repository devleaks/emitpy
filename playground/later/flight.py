from datetime import datetime, timedelta
import logging
logger = logging.getLogger("Flight")

from .airport import Airport
from .airline import Airline
from .aircraft import Aircraft
from .info import Info
from .airport import Parking
from .airspace import SID, STAR

FLIGHT_PHASE = [
    "UNKNOWN",
    "OFFBLOCK",
    "PUSHBACK",
    "TAXI",
    "TAXIHOLD",
    "TAKE_OFF",
    "TAKEOFF_ROLL",
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
    "STOPPED_ON_RWY",
    "STOPPED_ON_TAXIWAY",
    "ONBLOCK"
]


class Flight(Info):

    def __init__(self, name: str, scheduled: str, departure: Airport, arrival: Airport, operator: Airline, aircraft: Aircraft, gate: Parking):
        Info.__init__(self)
        self.name = name
        self.apt_departure = departure
        self.apt_arrival = arrival
        self.scheduled = scheduled
        self.actual = None
        self.operator = operator
        self.aircraft = aircraft
        self.gate = gate
        self.codeshare = None


    @staticmethod
    def roundTime(dt: datetime, roundTo: int = 300):
        """Round a datetime object to any time lapse in seconds
        dt : datetime.datetime object, default now.
        roundTo : Closest number of seconds to round to, default 5 minutes.
        Author: Thierry Husson 2012 - Use it as you want but don't blame me.
        """
        if dt == None:
            dt = datetime.now()
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



class Arrival(Flight):
    def __init__(self, name: str, scheduled: str, departure: Airport, arrival: Airport, operator: Airline, aircraft: Aircraft, gate: Parking):
        Flight.__init__(self, name, scheduled, departure, arrival, operator, aircraft, parking)

    def setSTAR(self, star: STAR):
        self.star = star

    def route(self):
        trip = Route()
        trip.add(self.cruize())
        trip.add(self.star())
        trip.add(self.approach())
        trip.add(self.land())
        trip.add(self.taxi())
        trip.add(self.park())
        return trip


class Departure(Flight):
    def __init__(self, name: str, scheduled: str, departure: Airport, arrival: Airport, operator: Airline, aircraft: Aircraft, gate: Parking):
        Flight.__init__(self, name, scheduled, departure, arrival, operator, aircraft, parking)

    def setSID(self, sid: SID):
        self.sid = sid

    def route(self):
        trip = Route()
        trip.add(self.pushback())
        trip.add(self.taxi())
        trip.add(self.takeoff())
        trip.add(self.sid())
        trip.add(self.cruize())
        return trip

class Route:
    def __init__(self):
        pass

    def add(self, obj):
        pass

