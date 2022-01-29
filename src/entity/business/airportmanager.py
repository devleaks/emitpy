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
        self.airline_locals = {}
        self.airlines = {}
        self.airline_cargos = {}
        self.airport_paxs = {}
        self.airport_cargos = {}
        self.airroutes = {
            "BY AIRLINE": {},
            "BY AIRPORT": {}
        }
        self.airport_base = None
        self.data = None


    def load(self):
        status = self.loadFromFile()
        if not status[0]:
            return [False, status[1]]
        return [False, "AirportManager::loaded"]


    def loadFromFile(self):
        self.airport_base = os.path.join(SYSTEM_DIRECTORY, self.icao)
        business = os.path.join(self.airport_base, "airport.yaml")

        if os.path.exists(business):
            with open(business, "r") as fp:
                self.data = yaml.safe_load(fp)
        else:
            logger.warning(":file: %s not found" % business)
            return [False, "AirportManager::loadRunways file %s not found", business]


        routes = os.path.join(self.airport_base, "airline-routes.csv")
        file = open(routes, "r")
        csvdata = csv.DictReader(file)  # AIRLINE CODE,AIRPORT
        cnt = 0
        for row in csvdata:
            aln = Airline.findIATA(row["AIRLINE CODE"])
            if aln is not None:
                self.addAirline(aln)
                apt = Airport.findIATA(row["AIRPORT"])
                if apt is not None:
                    self.addAirport(apt)
                    self.addAirroute(airline=aln, airport=apt)
                    cnt = cnt + 1
                else:
                    logger.warning(":loadFromFile: airport %s not found" % row["AIRPORT"])
            else:
                logger.warning(":loadFromFile: airline %s not found" % row["AIRLINE CODE"])
        file.close()
        logger.debug(":loadAll: loaded %d airline routes" % cnt)

        logger.debug(":loadFromFile: loaded")
        return [True, "AirportManager::loadFromFile: loaded"]


    def addAirline(self, airline: Airline, location: Union[LOCAL, REMOTE] = REMOTE):
        if location == LOCAL:
            self.airline_locals[airline.icao] = airline
        else:
            self.airlines[airline.icao] = airline

    def addAirport(self, airport: Airport, load: PAYLOAD = PAYLOAD.PAX):
        if load == PAYLOAD.PAX:
            self.airport_paxs[airport.icao] = airport
        else:
            self.airport_paxs[airport.icao] = airport

    def addAirroute(self, airline: Airline, airport: Airport, load: PAYLOAD = PAYLOAD.PAX):
        if airline.icao not in self.airroutes["BY AIRLINE"]:
            self.airroutes["BY AIRLINE"][airline.icao] = []
        self.airroutes["BY AIRLINE"][airline.icao].append(airport.icao)

        if airport.icao not in self.airroutes["BY AIRPORT"]:
            self.airroutes["BY AIRPORT"][airport.icao] =[]
        self.airroutes["BY AIRPORT"][airport.icao].append(airline.icao)

    def getRandomAirline(self):
        a = random.choice(list(self.airlines.keys()))
        return self.airlines[a]

    def getRandomDestination(self, airline: Airline = None):
        aln = airline if airline is not None else self.getRandomAirline()
        apt = random.choice(list(self.airroutes["BY AIRLINE"][aln.icao]))
        return (aln, Airport.find(apt))
