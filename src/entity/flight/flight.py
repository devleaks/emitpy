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
        self.flight_type = "PAX"  # |"CARGO"  # Determined from operator and flight number (for ex. > 5000)
        self.operator = operator
        self.aircraft = aircraft
        self.ramp = None
        self.codeshare = None
        self.phase = "SCHEDULED" if scheduled else "UNKNOWN"
        self.flightroute = None
        self.procedure = None


    def setRamp(self, ramp):
        if ramp in self.managedAirport.parkings.keys():
            self.ramp = ramp
            logger.debug("Flight::setRamp: %s" % self.ramp)
        else:
            logger.warning("Flight::setRamp: %s not found" % self.ramp)


    def setGate(self, gate):
        self.gate = gate
        logger.debug("Flight::setGate: %s" % self.ramp)


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


    def taxi(self):
        pass

    def plan(self):
        pass

    def fly(self):
        pass


class Arrival(Flight):
    def __init__(self, number: str, scheduled: str, managedAirport: Airport, origin: Airport, operator: Airline, aircraft: Aircraft):
        Flight.__init__(self, number=number, scheduled=scheduled, departure=origin, arrival=managedAirport, operator=operator, aircraft=aircraft)
        self.managedAirport = managedAirport


    def trimFlightRoute(self):
        """
        Remove last point for now, which is arrival airport
        """
        return self.flightroute["features"][0:-1]

    def plan(self):
        #
        # LNAV DEPARTURE TO ARRIVAL
        #
        if self.flightroute is None:
            self.loadFlightRoute()
        if len(self.flightroute["features"]) < 4:  # 4 features means 3 nodes (dept, fix, arr) and LineString.
            logger.warning("Arrival::plan: flightroute is too short %d" % len(self.flightroute["features"]))

        arrpts = self.trimFlightRoute()

        rwy = self.managedAirport.getRunway(self)
        logger.debug("Arrival::plan: runway %s" % rwy.name)
        star = self.managedAirport.getProcedure(self, rwy)
        logger.debug("Arrival::plan: STAR %s" % star.name)
        ret = self.managedAirport.procedures.getRoute(star, self.managedAirport.airspace)
        arrpts = arrpts + ret

        appch = self.managedAirport.getApproach(star, rwy)
        logger.debug("Arrival::plan: APPCH %s" % appch.name)
        ret = self.managedAirport.procedures.getRoute(appch, self.managedAirport.airspace)
        arrpts = arrpts + ret

        arrpts = arrpts + rwy.getRoute()
        self.procedure = (star, appch, rwy)
        self.flightroute = arrpts

        self.taxi()  # Runway exit to Ramp

        return (True, "Arrival::plan: planned")
        # ap = ArrivalPath(arr)
        # pa = ap.mkPath()


class Departure(Flight):
    def __init__(self, number: str, scheduled: str, managedAirport: Airport, destination: Airport, operator: Airline, aircraft: Aircraft):
        Flight.__init__(self, number=number, scheduled=scheduled, departure=managedAirport, arrival=destination, operator=operator, aircraft=aircraft)
        self.managedAirport = managedAirport

    def trimFlightRoute(self):
        """
        Remove first point for now, which is departure airport
        """
        return self.flightroute["features"][1:]

    def plan(self):
        #
        # LNAV DEPARTURE TO ARRIVAL
        #
        if self.flightroute is None:
            self.loadFlightRoute()
        if len(self.flightroute["features"]) < 4:  # 4 features means 3 nodes (dept, fix, arr) and LineString.
            logger.warning("Arrival::plan: flightroute is too short %d" % len(self.flightroute["features"]))

        rwy = self.managedAirport.getRunway(self)
        logger.debug("Departure::plan: runway %s" % rwy.name)
        deppts = [rwy.getRoute()]

        self.taxi()  # Ramp to runway hold

        sid = self.managedAirport.getProcedure(self, rwy)
        logger.debug("Departure::plan: SID %s" % sid.name)
        ret = self.managedAirport.procedures.getRoute(sid, self.managedAirport.airspace)
        deppts = deppts + ret

        deppts = deppts + self.trimFlightRoute()

        self.procedure = (rwy, sid)
        self.flightroute = deppts
        return (True, "Departure::plan: planned")
        # dp = DeparturePath(dep)
        # pd = dp.mkPath()
