"""
Different types of airports, depending on their status in the simulation.

- AirportBase: Simple, regular destination
- Airport: Main airport in simulation.
"""
from __future__ import annotations

import os
import csv
import logging
import random

from ..graph import Graph
from ..geo import Location

from ..constants import AIRPORT_DATABASE, FOOT
from ..parameters import DATA_DIR

logger = logging.getLogger("Airport")


# ################################@
# AIRPORT BASE
#
#
class Airport(Location):
    """
    An AirportBase is a location for flight departure and arrival.

    """

    _DB = {}

    def __init__(self, icao: str, iata: str, name: str, city: str, country: str, region: str, lat: float, lon: float, alt: float):
        Location.__init__(self, name, city, country, lat, lon, alt)
        self.icao = icao
        self.iata = iata
        self.region = region

        self._rawdata = {}
        self.airlines = {}
        self.routes = {}
        self.simairporttype = "Generic"

    @staticmethod
    def loadAll():
        """
        "id","ident","type","name","latitude_deg","longitude_deg","elevation_ft","continent","iso_country","iso_region","municipality","scheduled_service","gps_code","iata_code","local_code","home_link","wikipedia_link","keywords"
        """
        filename = os.path.join(DATA_DIR, AIRPORT_DATABASE, "airports.csv")
        file = open(filename, "r")
        csvdata = csv.DictReader(file)
        for row in csvdata:
            if row["longitude_deg"] != "" and row["elevation_ft"] != "":
                Airport._DB[row["ident"]] = Airport(icao=row["ident"], iata=row["iata_code"], name=row["name"],
                                                    city=row["municipality"], country=row["iso_country"], region=row["iso_region"],
                                                    lat=float(row["latitude_deg"]), lon=float(row["longitude_deg"]), alt=float(row["elevation_ft"])*FOOT)
        file.close()
        logger.debug("Airport::loadAll: loaded %d airports" % len(Airport._DB))


    @staticmethod
    def find(icao: str):
        return Airport._DB[icao] if icao in Airport._DB else None


    def loadFromFile(self):
        return [False, "no load implemented"]


# ################################@
# AIRPORT
#
#
class AirportBase(Airport):
    """
    An ManagedAirport is an airport as it appears in the simulation software.
    """
    def __init__(self, icao: str, iata: str, name: str, city: str, country: str, region: str, lat: float, lon: float, alt: float):
        Airport.__init__(self, icao=icao, iata=iata, name=name, city=city, country=country, region=region, lat=lat, lon=lon, alt=alt)
        self.airspace = None
        self.procedures = None
        self.runways = {}
        self.taxiways = Graph()
        self.parkings = {}
        self.service_roads = Graph()
        self.service_destinations = {}
        self.qfu = None
        self.qnh = None

    def setAirspace(self, airspace):
        self.airspace = airspace

    def load(self):
        status = self.loadFromFile()

        if not status[0]:
            return [False, status[1]]

        status = self.loadProcedures()
        if not status[0]:
            return [False, status[1]]

        status = self.loadRunways()
        if not status[0]:
            return [False, status[1]]

        status = self.loadParkings()
        if not status[0]:
            return [False, status[1]]

        status = self.loadTaxiways()
        if not status[0]:
            return [False, status[1]]

        status = self.loadServiceRoads()
        if not status[0]:
            return [False, status[1]]

        status = self.loadServiceDestinations()
        if not status[0]:
            return [False, status[1]]

        return [True, "Airport::load loaded"]


    def loadFromFile(self):
        return [False, "no load implemented"]

    def loadProcedures(self):
        return [False, "no load implemented"]

    def loadRunways(self):
        return [False, "no load implemented"]

    def loadTaxiways(self):
        return [False, "no load implemented"]

    def loadParkings(self):
        return [False, "no load implemented"]

    def loadServiceRoads(self):
        return [False, "no load implemented"]

    def loadServiceDestinations(self):
        return [False, "no load implemented"]


    def setQFU(self, qfu: float):
        self.qfu = qfu

    def setQNH(self, qnh: float):
        self.qnh = qnh

    def getProcedure(self, flight: 'Flight', runway: str):
        logger.debug("Airport::getProcedure: direction: %s" % type(flight).__name__)
        procs = self.procedures.procs["STAR"] if type(flight).__name__ == 'Arrival' else self.procedures.procs["SID"]
        validprocs = list(filter(lambda x: x.runway == runway.name, procs.values()))
        if len(validprocs) > 0:
            return random.choice(validprocs)
        logger.warning("Airport::getProcedure: no procedure found for runway %s" % runway)
        return None

    def getApproach(self, procedure: 'Procedure', runway: str):  # Procedure should be a STAR
        procs = self.procedures.procs["APPCH"]
        validappchs = list(filter(lambda x: x.runway == runway.name, procs.values()))
        if len(validappchs) > 0:
            return random.choice(validappchs)
        logger.warning("Airport::getApproach: no aproach found for runway %s" % runway)
        return None

    def getRunway(self, flight: 'Flight'):
        """
        Gets a valid runway for flight, depending on QFU, flight type (pax, cargo), destination, etc.

        :param      flight:  The flight
        :type       flight:  Flight

        :returns:   The runway.
        :rtype:     { return_type_description }
        """
        rwy = random.choice(list(self.runways))  ## formally random.choice(list(self.procedures.procs["RWY"])) is faster
        return self.procedures.procs["RWY"]["RW"+rwy]

    def getRamp(self, flight: 'Flight'):
        """
        Gets a valid ramp for flight depending on its attibutes.

        :param      flight:  The flight
        :type       flight:  Flight

        :returns:   The runway.
        :rtype:     { return_type_description }
        """
        ramp = random.choice(list(self.parkings))  ## formally random.choice(list(self.procedures.procs["RWY"])) is faster
        return ramp
