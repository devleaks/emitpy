"""
Airport Manager is a container for business and operations.
"""
import os
import json
import logging

from typing import Union

from .airline import Airline
from ..airport import AirportBase as Airport


from ..constants import PAX, CARGO, LOCAL, REMOTE


logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("FlightRoute")


class AirportManager:

    def __init__(self):
        self.airline_locals = {}
        self.airlines = {}
        self.airline_cargos = {}
        self.airport_paxs = {}
        self.airport_cargos = {}
        self.airroutes = []


    def loadFromFile(self):
        self.airport_base = os.path.join(SYSTEM_DIRECTORY, self.icao)
        business = os.path.join(self.airport_base, "airport.yaml")

        if os.path.exists(df):
            with open(df, "r") as fp:
                if name[-5:] == ".yaml":
                    self.data = yaml.safe_load(fp)
                else:  # JSON or GeoJSON
                    self.data = json.load(fp)
        else:
            logger.warning("GeoJSONAirport::file: %s not found" % df)
            return [False, "GeoJSONAirport::loadRunways file %s not found", df]

        logging.debug("GeoJSONAirport::loadFromFile: loaded")
        return [True, "GeoJSONAirport::loadFromFile: loaded"]

    def addAirline(self, airline: Airline, location: Union[LOCAL, REMOTE] = REMOTE):
        if location == LOCAL:
            self.airline_locals[airline.icao] = airline
        else:
            self.airlines[airline.icao] = airline

    def addAirport(self, airport: Airport, load: Union[PAX, CARGO] = PAX):
        if load == PAX:
            self.airport_paxs[airport.icao] = airport
        else:
            self.airport_paxs[airport.icao] = airport

    def addAirroute(self, airline: Airline, airport: Airport, load: Union[PAX, CARGO] = PAX):
        self.addAirline(airline)
        self.addAirport(airline, load)
        self.airroutes.append({
            "airline": airline.icao,
            "airport": airport.icao,
            "type": load
        })
