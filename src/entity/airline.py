"""

"""
import os
import yaml
import random
import logging
logger = logging.getLogger("Airline")

from .aircraft import AircraftType, Aircraft
from .company import Company
from .constants import AIRLINE, AIRLINE_DATABASE, CARGO
from .parameters import DATA_DIR


class Airline(Company):
    """
    An Airline is an operator of Flight movements with an Aircraft
    """

    def __init__(self, icao: str):
        self.icao = icao
        self._rawdata = None
        filename = os.path.join(DATA_DIR, AIRLINE_DATABASE, icao + ".yaml")
        file = open(filename, "r")
        a = yaml.safe_load(file)
        file.close()

        self._rawdata = a
        self.iata = self._rawdata["iata"]
        # logging.debug(yaml.dump(a, indent=4))
        Company.__init__(self, icao, AIRLINE, a["type"], self.iata)


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