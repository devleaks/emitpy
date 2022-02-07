"""
Airport Manager is a container for business and operations.
"""
import os
import yaml
import csv
import logging
import random

from typing import Union

from .airline import Airline
from ..airport import Airport

from ..constants import PAYLOAD, LOCAL, REMOTE
from ..parameters import DATA_DIR

SYSTEM_DIRECTORY = os.path.join(DATA_DIR, "managedairport")

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("AirportManager")


class AirportManager:

    def __init__(self, icao):
        self.icao = icao
        self.airlines = {}

        self.airport_base = None
        self.data = None
        self.airline_route_frequencies = None
        self.airline_frequencies = None


    def load(self):

        status = self.loadFromFile()
        if not status[0]:
            return status

        status = self.loadAirRoutes()
        if not status[0]:
            return status

        return [False, "AirportManager::loaded"]


    def loadFromFile(self):
        self.airport_base = os.path.join(SYSTEM_DIRECTORY, self.icao)
        business = os.path.join(self.airport_base, "airport.yaml")
        if os.path.exists(business):
            with open(business, "r") as fp:
                self.data = yaml.safe_load(fp)
            logger.warning(":file: %s loaded" % business)
            return [True, "AirportManager::loadFromFile: loaded"]
        logger.warning(":file: %s not found" % business)
        return [False, "AirportManager::loadFromFile file %s not found", business]


    def loadAirRoutes(self):
        routes = os.path.join(self.airport_base, "airline-routes.csv")
        file = open(routes, "r")
        csvdata = csv.DictReader(file)  # AIRLINE CODE,AIRPORT
        cnt = 0
        for row in csvdata:
            airline = Airline.findIATA(row["AIRLINE CODE"])
            if airline is not None:
                if airline.iata not in self.airlines.keys():
                    self.airlines[airline.icao] = airline
                airport = Airport.findIATA(row["AIRPORT"])
                if airport is not None:
                    airline.addRoute(airport)
                    airport.addAirline(airline)
                    cnt = cnt + 1
                else:
                    logger.warning(":loadAirRoutes: airport %s not found" % row["AIRPORT"])
            else:
                logger.warning(":loadAirRoutes: airline %s not found" % row["AIRLINE CODE"])
        file.close()
        logger.debug(":loadAirRoutes: loaded %d airline routes for %d airlines" % (cnt, len(self.airlines)))

        fn = os.path.join(self.airport_base, "airline-frequencies.csv")
        if os.path.exists(fn):
            self.airline_frequencies = {}
            with open(fn, "r") as file:
                data = csv.DictReader(file)  # AIRLINE CODE,AIRPORT
                for row in data:
                    self.airline_frequencies[row["AIRLINE CODE"]] = int(row["COUNT"])
                logger.debug(":loadAirRoutes: airline-frequencies loaded")

        fn = os.path.join(self.airport_base, "airline-route-frequencies.csv")
        if os.path.exists(fn):
            self.airline_route_frequencies = {}
            with open(fn, "r") as file:
                data = csv.DictReader(file)  # AIRLINE CODE,AIRPORT
                for row in data:
                    if row["AIRLINE CODE"] not in self.airline_route_frequencies:
                        self.airline_route_frequencies[row["AIRLINE CODE"]] = {}

                    if row["AIRPORT"] not in self.airline_route_frequencies[row["AIRLINE CODE"]]:
                        self.airline_route_frequencies[row["AIRLINE CODE"]][row["AIRPORT"]] = 0
                    self.airline_route_frequencies[row["AIRLINE CODE"]][row["AIRPORT"]] = self.airline_route_frequencies[row["AIRLINE CODE"]][row["AIRPORT"]] + int(row["COUNT"])
                logger.debug(":loadAirRoutes: airline-route-frequencies loaded")

        logger.debug(":loadAirRoutes: loaded")
        return [True, "AirportManager::loadAirRoutes: loaded"]


    def getRandomAirline(self):
        aln = None
        if self.airline_frequencies is not None:
            a = a = random.choices(population=list(self.airline_frequencies.keys()), weights=list(self.airline_frequencies.values()))
            aln = Airline.findIATA(a[0])
            if aln is not None:
                logger.debug(":getRandomAirline: with density: %s(%s)" % (aln.icao, aln.iata))
            else:
                logger.warning(":getRandomAirline: with density: %s not found" % (a[0]))
        else:
            a = random.choice(list(self.airlines.keys()))
            aln = Airline.find(a)
            logger.debug(":getRandomAirline: %s" % a)
        return aln


    def getRandomAirport(self, airline: Airline = None):
        aln = airline if airline is not None else self.getRandomAirline()
        apt = None
        if self.airline_route_frequencies is not None:
            aptlist = self.airline_route_frequencies[aln.iata]
            a = random.choices(population=list(aptlist.keys()), weights=list(aptlist.values()))
            apt = Airport.findIATA(a[0])
            if apt is None:
                logger.debug(":getRandomAirport: with density: %s(%s)" % (apt.icao, apt.iata))
            else:
                logger.warning(":getRandomAirport: with density: %s not found" % (a[0]))
        else:
            a = random.choice(list(aln.routes.keys()))
            apt = Airport.find(a)
            logger.debug(":getRandomAirport: %s" % a)
        return (aln, apt)

    def hub(self, airport, airline):
        airport.addHub(airline)
        airline.addHub(airport)