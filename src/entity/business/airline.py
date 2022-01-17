"""
Definition if Airline and Airroute operated by Airlines
"""
import os
import yaml
import random
import logging
from turfpy import measurement

from ..aircraft import AircraftType, Aircraft
from ..airport import Airport
from .company import Company
from ..constants import AIRLINE, AIRLINE_DATABASE, CARGO
from ..parameters import DATA_DIR
from ..geo.units import toNm

logger = logging.getLogger("Airline")


class Airline(Company):
    """
    An Airline is an operator of Airroute
    """

    def __init__(self, icao: str):
        self.icao = icao
        self.airroutes = []
        self.hubs = {}
        self._rawdata = None
        filename = os.path.join(DATA_DIR, AIRLINE_DATABASE, icao + ".yaml")
        file = open(filename, "r")
        a = yaml.safe_load(file)
        file.close()

        self._rawdata = a
        self.iata = self._rawdata["iata"]
        # logging.debug(yaml.dump(a, indent=4))
        Company.__init__(self, icao, AIRLINE, a["type"], self.iata)


    def addHub(self, airport: Airport):
        self.hubs[airport.icao] = airport


    def randomFlightname(self, reglen: int = 4):
        """
        Generates a random aircraft registration OO-ABCD.

        :param      reglen:       The reglen
        :type       reglen:       int
        """
        s = "0123456789"
        return self.iata + "-" + "".join(random.sample(s, reglen)).lstrip("0") # no SN-0010, SN-10


    def plane_type_for(self, payload: str, range: float) -> AircraftType:
        return AircraftType.find_by_icao("A320")

    def plane(self, acType: AircraftType) -> Aircraft:
        r = Aircraft.randomRegistration(self._rawdata["registration"])
        return Aircraft(operator=self.name, acType=acType, registration=r)


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
