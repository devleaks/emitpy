"""
Definition if Airline and Airroute operated by Airlines
"""
import os
import random
import logging
import csv
import operator
import yaml

from turfpy import measurement

from .company import Company
from emitpy.airport import Airport
from emitpy.constants import AIRLINE, AIRLINE_DATABASE, REDIS_PREFIX, REDIS_DATABASE, REDIS_LOVS, REDIS_DB
from emitpy.parameters import DATA_DIR
from emitpy.utils import toNm, key_path, rejson

logger = logging.getLogger("Airline")


class Airline(Company):
    """
    An Airline is an operator of Airroute
    """
    _DB = {}
    _DB_IATA = {}

    def __init__(self, name: str, iata: str, icao: str):
        Company.__init__(self, name, AIRLINE, "", iata)
        self.icao = icao
        self.iata = iata
        self.routes = {}  # airports
        self.hub = {}    # airports
        self._rawdata = None


    @staticmethod
    def loadAll():
        """
        Loads all airlines from a file.
        """
        filename = os.path.join(DATA_DIR, AIRLINE_DATABASE, "airlines.csv")
        file = open(filename, "r")
        csvdata = csv.DictReader(file)
        for row in csvdata:
            # ICAO,IATA,Airline,Callsign,Country
            a = Airline(name=row["Airline"], icao=row["ICAO"], iata=row["IATA"])
            Airline._DB[row["ICAO"]] = a
            Airline._DB_IATA[row["IATA"]] = a
        file.close()
        logger.debug(f":loadAll: loaded {len(Airline._DB)} airlines")

    @staticmethod
    def find(code: str, redis = None):
        """
        Finds an airline through its either IIATA 2 letter code or ICAO 3 letter code.
        """
        if redis is not None:
            if len(code) == 3:
                k = key_path(key_path(REDIS_PREFIX.AIRLINES.value, REDIS_PREFIX.ICAO.value), code)
            else:
                k = key_path(key_path(REDIS_PREFIX.AIRLINES.value, REDIS_PREFIX.IATA.value), code)
            ac = rejson(redis=redis, key=k, db=REDIS_DB.REF.value)
            if ac is not None:
                return Airline.fromInfo(info=ac)
            else:
                logger.warning(f":find: no such key {k}")
        else:
            if len(code) == 3:
                return Airline._DB[code] if code in Airline._DB else None
            return Airline._DB_IATA[code] if code in Airline._DB_IATA else None
        return None


    @staticmethod
    def findICAO(icao: str, redis = None):
        """
        Finds an airline through ICAO 3 letter code.
        """
        if redis is not None:
            k = key_path(key_path(REDIS_PREFIX.AIRLINES.value, REDIS_PREFIX.ICAO.value), icao)
            ac = rejson(redis=redis, key=k, db=REDIS_DB.REF.value)
            if ac is not None:
                return Airline.fromInfo(info=ac)
            else:
                logger.warning(f":findICAO: no such key {k}")
        else:
            return Airline._DB[icao] if icao in Airline._DB else None
        return None

    @staticmethod
    def findIATA(iata: str, redis = None):
        """
        Finds an airline through its IATA 2 letter code.
        """
        if redis is not None:
            k = key_path(key_path(REDIS_PREFIX.AIRLINES.value, REDIS_PREFIX.IATA.value), iata)
            ac = rejson(redis=redis, key=k, db=REDIS_DB.REF.value)
            if ac is not None:
                return Airline.fromInfo(info=ac)
            else:
                logger.warning(f":findIATA: no such key {k}")
        else:
            return Airline._DB_IATA[iata] if iata in Airline._DB_IATA else None
        return None

    @staticmethod
    def getCombo(redis = None):
        """
        Builds a list of (code, description) pairs of all airlines.
        """
        if redis is not None:
            k = key_path(REDIS_DATABASE.LOVS.value, REDIS_LOVS.AIRLINES.value)
            return rejson(redis=redis, key=k, db=REDIS_DB.REF.value)

        l = filter(lambda a: len(a.routes) > 0, Airline._DB_IATA.values())
        a = [(a.iata, a.orgId) for a in sorted(l, key=operator.attrgetter('orgId'))]
        return a


    @classmethod
    def fromInfo(cls, info):
        """
        Builds and Airline instance from the dictionary object returned by :py:func:`getInfo()`.

        :param      cls:   The cls
        :type       cls:   { type_description }
        :param      info:  The information
        :type       info:  { type_description }
        """
        return Airline(name=info["orgId"], iata=info["iata"], icao=info["icao"])


    def getInfo(self):
        """
        Returns a dictionary object with instance data.
        """
        i = super().getInfo()
        i["iata"] = self.iata
        i["icao"] = self.icao
        return i


    def loadFromFile(self):
        """
        Loads an airlibe specific file.
        """
        filename = os.path.join(DATA_DIR, AIRLINE_DATABASE, self.icao + ".yaml")
        file = open(filename, "r")
        self._rawdata = yaml.safe_load(file)
        file.close()

    def addRoute(self, airport: Airport):
        """
        Adds a route to airport for this airline.

        :param      airport:  The airport
        :type       airport:  Airport
        """
        self.routes[airport.icao] = airport

    def addHub(self, airport: Airport):
        """
        Adds a hub airport for this airline.

        :param      airport:  The airport
        :type       airport:  Airport
        """
        self.hub[airport.icao] = airport

    def randomFlightname(self, reglen: int = 4, icao: bool = False):
        """
        Generates a random flight number for this airline, returns IATA or ICAO (icao flag to True) flight name.

        :param      reglen:       The reglen
        :type       reglen:       int
        """
        s = "0123456789"
        return (self.icao if icao else self.iata) + "-" + "".join(random.sample(s, reglen)).lstrip("0") # no SN-0010, SN-10


    def save(self, base, redis, mode: str = "icao"):
        """
        Saves airport data to cache.

        :param      base:   The base
        :type       base:   { type_description }
        :param      redis:  The redis
        :type       redis:  { type_description }
        """
        if mode == "icao":
            redis.json().set(key_path(base, self.icao), "$", self.getInfo())
        else:
            redis.json().set(key_path(base, self.iata), "$", self.getInfo())


class Airroute:
    """
    An AirRoute is an route between two airports operated by an Airline.
    """

    def __init__(self, origin: Airport, destination: Airport, operator: Airline):
        self.origin = origin
        self.destination = destination
        self.operator = operator
        self.sharecodes = []

        operator.addAirroute(self)

    def addSharecode(self, operator: Airline):
        """
        Adds a sharecode for this route.

        :param      operator:  The operator
        :type       operator:  Airline
        """
        self.sharecodes.append(operator)

    def distance(self):
        """
        Returns flight length in nautical miles

        :returns:   { description_of_the_return_value }
        :rtype:     { return_type_description }
        """
        """
        Returns the distance from this airport to the supplied airport in nautical miles.

        :param      icao:  The icao
        :type       icao:  str
        """
        destination = Airport.find_by_icao(icao)
        if destination is not None:
            # logger.debug("destination %s: %f,%f", destination.name, destination.lat, destination.lon)
            return toNm(measurement.distance(self.origin, self.destination))
        return 0.0
