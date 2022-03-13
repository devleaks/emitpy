"""
Definition if Airline and Airroute operated by Airlines
"""
import os
import yaml
import random
import logging
import csv
import operator

from turfpy import measurement

from .company import Company
from ..airport import Airport
from ..constants import AIRLINE, AIRLINE_DATABASE
from ..parameters import DATA_DIR
from ..utils import toNm

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
    def find(code: str):
        # Usually, ICAO codes are 3 letters "QTR", IATA codes are 2 letter "QR"
        if len(code) == 3:
            return Airline._DB[code] if code in Airline._DB else None
        return Airline._DB_IATA[code] if code in Airline._DB_IATA else None

    @staticmethod
    def findICAO(icao: str):
        return Airline._DB[icao] if icao in Airline._DB else None

    @staticmethod
    def findIATA(iata: str):
        return Airline._DB_IATA[iata] if iata in Airline._DB_IATA else None

    @staticmethod
    def getCombo():
        a = [(a.iata, a.orgId) for a in sorted(Airline._DB_IATA.values(), key=operator.attrgetter('orgId'))]
        return a

    def loadFromFile(self):
        filename = os.path.join(DATA_DIR, AIRLINE_DATABASE, self.icao + ".yaml")
        file = open(filename, "r")
        self._rawdata = yaml.safe_load(file)
        file.close()


    def addRoute(self, airport: Airport):
        self.routes[airport.icao] = airport


    def addHub(self, airport: Airport):
        self.hub[airport.icao] = airport


    def randomFlightname(self, reglen: int = 4):
        """
        Generates a random aircraft registration OO-ABCD.

        :param      reglen:       The reglen
        :type       reglen:       int
        """
        s = "0123456789"
        return self.iata + "-" + "".join(random.sample(s, reglen)).lstrip("0") # no SN-0010, SN-10


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
