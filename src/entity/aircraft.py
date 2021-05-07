"""
An Aircraft is a passenger or cargo plane.
"""
import os
import csv
import random

from .identity import Identity

from .constants import AIRCRAFT, PAX, CARGO, AIRCRAFT_TYPE_DATABASE
from .parameters import DATA_DIR


class AircraftType:
    """
    ICAO

    Horizontal speeds (knots):
    staxi
    stakeoff
    sclimb
    scruise
    sdescend
    sfinal
    sapproach
    slanding

    Vertical speeds (feet per min):
    initial_climb
    climb
    descend
    descend_expedite
    approach
    final

    passenger capacity=150 or [100,20,10]
    cargo capacity
    fuel capacity

    mtow?

    range(nm)

    airlines
    alike

    length
    width
    icao_category=[A-F]


    "simulation size factor": A320=1, A350=1.8, etc.
    """
    _DB = None

    def __init__(self, icao: str, manufacturer: str, data: object):

        self.icao = icao
        self.manufacturer = manufacturer
        self._raw = data

    def size(self, size_default: int = 2):
        if "pax" in self._raw:
            return int(self._raw["pax"] / 100)
        return size_default

    def range(self):
        return 10000

    @staticmethod
    def load():
        if AircraftType._DB is None:  # loads database
            AircraftType._DB = {}
            filename = os.path.join(DATA_DIR, AIRCRAFT_TYPE_DATABASE, AIRCRAFT_TYPE_DATABASE + ".csv")
            file = open(filename, "r")
            csvdata = csv.DictReader(file)
            for row in csvdata:
                AircraftType._DB[row["ICAO Code"]] = row
            file.close()

    @staticmethod
    def find_by_icao(icao: str):
        AircraftType.load()

        if icao in AircraftType._DB.keys():
            a = AircraftType._DB[icao]
            return AircraftType(icao=a["ICAO Code"], manufacturer=a["Manufacturer"], data=a)
        return None


class Aircraft(Identity):
    """
    An aircraft, identified and registered.
    """

    def __init__(self, operator: str, acType: AircraftType, registration: str, cargo: bool = False):
        ty = CARGO if cargo else PAX
        reg = registration if registration is not None else Aircraft.randomRegistration(country="Z")
        Identity.__init__(self, operator, AIRCRAFT, ty, reg)  # {aircraft:pax|aircraft:cargo}
        self.aircraft_type = acType

    @staticmethod
    def createRandom(model: str, country: str):
        acType = AircraftType.find(model)


    @staticmethod
    def randomRegistration(country: str, reglen: int = 4, with_number: bool = False):
        """
        Generates a random aircraft registration OO-ABCD.

        :param      country:      The country
        :type       country:      str
        :param      reglen:       The reglen
        :type       reglen:       int
        :param      with_number:  The with number
        :type       with_number:  bool
        """
        s = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        if with_number:
            s += "0123456789"
        return country + "-" + "".join(random.sample(s, reglen))
