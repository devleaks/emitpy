"""
A ManagedAirport is the «Home» airport in the simulation.
There should only be one Home airport.

"""
import os
import yaml
import csv
import json
import random
from datetime import timedelta

import logging
logger = logging.getLogger("ManagedAirport")

# from ..metar import Metar
from .airport import ManagedAirport
from .runway import Runway
from ..clearance import Clearance
from ..aircraft import AircraftType

from ..constants import PASSENGER, CARGO, DEPARTURE, ARRIVAL
from ..constants import MANAGED_AIRPORT, GEOMETRY_DATABASE

from ..parameters import DATA_DIR

WIND_SPEED = 1
WIND_DIRECTION = 0

PARAM_MOVEMENTS = "movements"

class XPManagedAirport(ManagedAirport):
    """
    The ManagerAirport is the main airport we simulate.
    It is built, loaded from a single config YAML file like a DetailedAirport.
    """

    def __init__(self, icao: str):
        self.metar = None
        self.qfu = None



    def init(self):

        # Loads additional info for managed airport
        filename = os.path.join(DATA_DIR, MANAGED_AIRPORT, self.icao, "simulation.yaml")
        if os.path.isfile(filename):
            file = open(filename, "r")
            a = yaml.safe_load(file)
            file.close()

            self._rawparams = a
            # logger.debug(yaml.dump(a, indent=4))

        self.loadRunways()
        self.loadParking()

        # # Conditions of the day
        # self.metar = Metar(self.icao)
        # wind = self.metar.wind()
        # self.setqfu(wind)

        self._inited = True
        logger.debug("ManagedAirport::inited: %s", self.icao)



    def loadAirport(self):
        """
        Loads main geographical airport components: Runways, taxiways, service roads, aprons, and parkings.
        """
        pass


    def loadBusiness(self):
        """
        Loads airport commercial components: Airlines, Airroutes, etc.
        """
        pass


    def loadServices(self):
        """
        Loads airport services components: Service types, Service vehicles, etc.
        """
        pass


    def loadRunways(self):
        if "runways" in self._rawparams:
            for rwy in self._rawparams["runways"]:
                self.runways[rwy] = Runway(rwy)

        if "runway_usage" in self._rawdata:
            # reset usage to none for all runways
            for rwy in self.runways.keys():
                for mode in (PASSENGER, CARGO):
                    self.runways[rwy].use(mode, False)
                for direction in (DEPARTURE, ARRIVAL):
                    self.runways[rwy].use(direction, False)
            # set usage as asked
            for mode in self._rawparams["runway_usage"]:
                for rwy in self._rawparams["runway_usage"][mode]:
                    self.runways[rwy].use(mode, True)

        self.clearance = Clearance(self.runways, self._rawparams["slot"])


    def loadParking(self):
        filename = os.path.join(DATA_DIR, GEOMETRY_DATABASE, self.icao, "parking-boxes.geojson")
        if os.path.isfile(filename):
            file = open(filename, "r")
            self.parkings = json.load(file)
            file.close()
        logger.debug("ManagedAirport::loadParking: %d parkings", len(self.parkings["features"]))

        # for name in self.parkings["features"]:
        #     self.parkings[name] = Parking.fromGeoJSON(self.parkings["features"][name])


    def loadTaxiways(self):
        pass


    def loadServiceRoads(self):
        pass


    def findParking(self, payload: str, acType: AircraftType):
        parking = random.choice(self.parkings["features"])
        return parking["properties"]["name"]


    def taxi_time(self, mode:str, payload:str , parking:str, landing_time:str, aplty: str):
        return timedelta(seconds=15*60)


    def setqfu(self, wind):
        """
        Sets qfu from wind conditions.

        :param      wind:  The wind
        :type       wind:  { type_description }
        """
        if self.metar:
            self.metar.update()
            logger.debug("ManagedAirport::setqfu: metar updated")

        all_runways = self.runways.values()
        valid_runways = []

        if wind[WIND_SPEED] < 1:  # in meter per second
            valid_runways = all_runways
        else:  # take wind into account
            wmin = wind[WIND_DIRECTION] - 90
            if wmin < 0:
                wmin += 360
            wmax = wind[WIND_DIRECTION] + 90
            if wmax > 360:
                wmax -= 360
            if wmin > wmax:
                wtmp = wmin
                wmin = wmax
                wmax = wtmp

            # Note: We accept wind perpendicular to runway otherwise in that case, we don't find any suitable runway...
            if wind[WIND_DIRECTION] < 180:
                for r in all_runways:
                    if r.heading >= wmin and r.heading <= wmax:  # between 120 and 300
                        valid_runways.append(r)
            else:
                for r in all_runways:
                    if r.heading >= wmax or r.heading <= wmin:  # between 300 and 360 or 0 and 120
                        valid_runways.append(r)


        if len(valid_runways) > 0:
            # Mark runways as valid for now
            for r in self.runways.values():
                r.use("qfu", False)
            for r in valid_runways:
                r.use("qfu", True)
            # Remember first one's heading (on very large airport there might be a lot of valid runways...)
            rwy = valid_runways[0]  # first one is prefered
            self.qfu = rwy.name[0:2]
        else:
            logger.critical("setqfu: no valid runways?")

        logger.debug("Wind: %.0f° %.2f m/s, qfu: %s", wind[WIND_DIRECTION], wind[WIND_SPEED], self.qfu)
