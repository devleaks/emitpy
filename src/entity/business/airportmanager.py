"""
Airport Manager is a container for business and operations.
"""
import os
import yaml
import logging

from typing import Union

from .airline import Airline
from ..airport import AirportBase as Airport


from ..constants import PAYLOAD, LOCAL, REMOTE
from ..parameters import DATA_DIR

SYSTEM_DIRECTORY = os.path.join(DATA_DIR, "x-plane")

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
        self.airroutes = []
        self.data = None


    def load(self):
        return [False, "AirportManager::load: not implemented"]


    def loadFromFile(self):
        self.airport_base = os.path.join(SYSTEM_DIRECTORY, self.icao)
        business = os.path.join(self.airport_base, "airport.yaml")

        if os.path.exists(business):
            with open(business, "r") as fp:
                self.data = yaml.safe_load(fp)
        else:
            logger.warning(":file: %s not found" % df)
            return [False, "AirportManager::loadRunways file %s not found", df]

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
        self.addAirline(airline)
        self.addAirport(airline, load)
        self.airroutes.append({
            "airline": airline.icao,
            "airport": airport.icao,
            "type": load
        })
