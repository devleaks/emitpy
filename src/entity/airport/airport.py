"""
Different types of airports, depending on their status in the simulation.

- Airport: Regular destination
- DetailedAirport: Destination with some added information (airlines)
- ManagedAirport: Main airport in simulation. In file home.py

"""
import os
import yaml
import csv
from turfpy import measurement

import logging
logger = logging.getLogger("Airport")

from ..location import Location
from ..airline import Airline

from ..utils.units import toNm
from ..constants import AIRLINES, CONNECTIONS, PASSENGER, CARGO, AIRPORT_DATABASE
from ..parameters import DATA_DIR


""" ********************************************************************** """
class Airport(Location):
    """
    An airport is a location for flight departure and arrival.

    """

    _DB = {}  # Database of all airports

    def __init__(self, icao: str, iata: str, name: str, city: str, country: str, region: str, lat: float, lon: float, alt: float, data: object):
        """
        Constructs a new instance.

        :param      icao:     The ICAO code of the airport
        :type       icao:     str
        :param      iata:     The IATA code of the airport
        :type       iata:     str
        :param      name:     The name of the airport (in English)
        :type       name:     str
        :param      city:     The city
        :type       city:     str
        :param      country:  The country
        :type       country:  str
        :param      region:   The region of the airport
        :type       region:   str
        :param      lat:      The latitude, in decimal degrees
        :type       lat:      float
        :param      lon:      The longitude, in decimal degrees
        :type       lon:      float
        :param      alt:      The altitude in meter above sea level
        :type       alt:      float
        """
        Location.__init__(self, name, city, country, lat, lon, alt)
        self._inited = False
        self.icao = icao
        self.iata = iata
        self.region = region
        self.init()

    def init(self):
        Airport._DB[self.icao] = self  # register itself in database
        # if type(self) != Airport:
        #     logger.debug("Airport::inited: %s, %s", self.icao, str(type(self)))


    def distance_to(self, icao: str) -> float:
        """
        Returns the distance from this airport to the supplied airport in nautical miles.

        :param      icao:  The icao
        :type       icao:  str
        """
        destination = Airport.find_by_icao(icao)
        if destination is not None:
            # logger.debug("destination %s: %f,%f", destination.name, destination.lat, destination.lon)
            return toNm(measurement.distance(self.feature, destination.feature))

        return 0.0


    @staticmethod
    def load():
        """
        Loads Airport's from file. Do not override airport that have been registered.
        """
        if len(Airport._DB) < 100:
            filename = os.path.join(DATA_DIR, AIRPORT_DATABASE, AIRPORT_DATABASE + ".csv")
            file = open(filename, "r")
            csvdata = csv.DictReader(file)
            cnt = 0
            for a in csvdata:
                if a["ident"] not in Airport._DB:
                    elev = float(a["elevation_ft"])*0.3048 if a["elevation_ft"] != '' else None
                    apt = Airport(icao=a["ident"], iata=a["iata_code"], name=a["name"], city=a["municipality"], country=a["iso_country"], region=a["iso_region"], lat=float(a["latitude_deg"]), lon=float(a["longitude_deg"]), alt=elev, data=a)
                    cnt += 1
            file.close()
            logger.debug("Airport::load: %d airports added", cnt)


    @staticmethod
    def find_by_icao(icao: str):
        Airport.load()
        if icao in Airport._DB.keys():
            return Airport._DB[icao]
        return None


    @staticmethod
    def find_by_iata(iata: str):
        Airport.load()
        for a in Airport._DB:
            if iata == a.iata:
                return a
        return None


""" *********************************************************************** """
class DetailedAirport(Airport):
    """
    An DetailedAirport is an airport for which we manage more details like operating airlines, routes, etc.
    It is built, loaded from a single config YAML file.
    """

    def __init__(self, icao: str):
        """
        Constructs a new instance.

        :param      icao:     The icao
        :type       icao:     str
        :param      iata:     The iata
        :type       iata:     str
        :param      name:     The name
        :type       name:     str
        :param      city:     The city
        :type       city:     str
        :param      country:  The country
        :type       country:  str
        :param      lat:      The lat
        :type       lat:      float
        :param      lon:      The lon
        :type       lon:      float
        :param      alt:      The alternate
        :type       alt:      float
        """
        self._rawdata = None
        self.airlines = {}
        self.routes = {
            PASSENGER: {},
            CARGO: {}
        }

        # collects info for super() initialisation
        filename = os.path.join(DATA_DIR, AIRPORT_DATABASE, icao + ".yaml")
        if not os.path.isfile(filename):
            logger.critical("__init__: filename %s does not exist", filename)
            return

        file = open(filename, "r")
        a = yaml.safe_load(file)
        file.close()
        self._rawdata = a
        Airport.__init__(self, icao=a["icao"], iata=a["iata"], name=a["name"], city=a["city"], country=a["country"], region=a["region"], lat=a["latitude"], lon=a["longitude"], alt=a["altitude"], data=a)


    def init(self):
        super().init()

        # 1. Load airlines
        if AIRLINES in self._rawdata.keys():
            for icao in self._rawdata[AIRLINES]:
                self.airlines[icao] = Airline(icao)

        # 2. Load airports this airport is connected to (routes)
        if CONNECTIONS in self._rawdata.keys():
            if PASSENGER in self._rawdata[CONNECTIONS]:
                for icao in self._rawdata[CONNECTIONS][PASSENGER]:
                    self.routes[PASSENGER][icao] = Airport.find_by_icao(icao)
                logger.debug("DetailedAirport::init: PAX routes: %s", self.routes[PASSENGER].keys())
            if CARGO in self._rawdata[CONNECTIONS]:
                for icao in self._rawdata[CONNECTIONS][CARGO]:
                    self.routes[CARGO][icao] = Airport.find_by_icao(icao)
                logger.debug("DetailedAirport::init: Cargo routes: %s", self.routes[CARGO].keys())
        self._inited = True
        logger.debug("DetailedAirport::inited: %s", self.icao)

