import os
import logging
import json
import random

from datetime import datetime, timedelta

from ..airport import Airport
from ..business import Airline
from ..aircraft import Aircraft

from ..parameters import DATA_DIR
from ..constants import AODB, MANAGED_AIRPORT, FLIGHTROUTE_DATABASE

logger = logging.getLogger("Flight")

FLIGHT_PHASE = [
    "SCHEDULED",
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
    "ONBLOCK",
    "TERMINATED"
]


class Flight:

    def __init__(self, operator: Airline, number: str, scheduled: str, departure: Airport, arrival: Airport, aircraft: Aircraft):
        self.number = number
        self.departure = departure
        self.arrival = arrival
        self.managedAirport = None
        self.scheduled = scheduled
        self.actual = None
        self.operator = operator
        self.aircraft = aircraft
        self.ramp = None
        self.codeshare = None
        self.phase = "SCHEDULED"
        self.flightroute = None
        self.procedure = None


    def setRamp(self, ramp):
        self.ramp = ramp


    def setGate(self, gate):
        self.gate = gate


    def setProcedure(self):
        self.procedure = self.getProcedure()
        logger.debug("Flight::setProcedure: %s" % self.procedure.name)


    def loadFlightRoute(self):
        flight = self.departure.icao.lower() + "-" + self.arrival.icao.lower()
        filename = os.path.join(DATA_DIR, MANAGED_AIRPORT, self.managedAirport.icao.upper(), FLIGHTROUTE_DATABASE, flight + ".geojson")
        if os.path.exists(filename):
            file = open(filename, "r")
            self.flightroute = json.load(file)
            file.close()
            logger.debug("Flight::loadFlightRoute: load %d nodes for %s" % (len(self.flightroute["features"]), flight))
        else:
            logger.warning("Flight::loadFlightRoute: file not found %s" % filename)


    def plan(self):
        #
        # LNAV
        #
        if self.flightroute is None:
            self.loadFlightRoute()
        if len(self.flightroute["features"]) < 4:  # 4 features means 3 nodes (dept, fix, arr) and LineString.
            logger.warning("Flight::plan: flightroute is too short %d" % len(self.flightroute["features"]))

        logger.debug("Flight::plan: %s %s" % (self.managedAirport.icao, type(self).__name__))
        if type(self).__name__ == "Arrival":  # last feature (-1) is route linestring, the one before (-2) is destination airport.
            logger.debug("Flight::plan: last point %s" % (self.flightroute["features"][-3]["properties"]))
        else:
            logger.debug("Flight::plan: first point %s" % (self.flightroute["features"][1]["properties"]))

        self.setProcedure()


    def fly(self):
        pass


class Arrival(Flight):
    def __init__(self, number: str, scheduled: str, managedAirport: Airport, origin: Airport, operator: Airline, aircraft: Aircraft):
        Flight.__init__(self, number=number, scheduled=scheduled, departure=origin, arrival=managedAirport, operator=operator, aircraft=aircraft)
        self.managedAirport = managedAirport

    def getProcedure(self):
        # should select for origin airport, random for now
        procname = random.choice(list(self.managedAirport.procedures.stars.keys()))
        return self.managedAirport.procedures.stars[procname]


class Departure(Flight):
    def __init__(self, number: str, scheduled: str, managedAirport: Airport, destination: Airport, operator: Airline, aircraft: Aircraft):
        Flight.__init__(self, number=number, scheduled=scheduled, departure=managedAirport, arrival=destination, operator=operator, aircraft=aircraft)
        self.managedAirport = managedAirport

    def getProcedure(self):
        # should select for destination airport, random for now
        procname = random.choice(list(self.managedAirport.procedures.sids.keys()))
        return self.managedAirport.procedures.sids[procname]
