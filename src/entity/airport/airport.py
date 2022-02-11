"""
Different types of airports, depending on their status in the simulation.

- AirportBase: Simple, regular destination
- Airport: Main airport in simulation.
"""
from __future__ import annotations

import os
import csv
import json
import logging
import random

from ..graph import Graph
from ..geo import Location

from ..airspace import CIFP
from ..constants import AIRPORT_DATABASE
from ..parameters import DATA_DIR
from ..utils import FT
logger = logging.getLogger("Airport")


# ################################@
# AIRPORT
#
#
class Airport(Location):
    """
    An Airport is a location for flight departure and arrival.
    """

    _DB = {}
    _DB_IATA = {}

    def __init__(self, icao: str, iata: str, name: str, city: str, country: str, region: str, lat: float, lon: float, alt: float):
        Location.__init__(self, name, city, country, lat, lon, alt)
        self.icao = icao
        self.iata = iata
        self.region = region

        self._rawdata = {}
        self.airlines = {}
        self.hub = {}
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
                a = Airport(icao=row["ident"], iata=row["iata_code"], name=row["name"],
                            city=row["municipality"], country=row["iso_country"], region=row["iso_region"],
                            lat=float(row["latitude_deg"]), lon=float(row["longitude_deg"]), alt=float(row["elevation_ft"])*FT)
                Airport._DB[row["ident"]] = a
                Airport._DB_IATA[row["iata_code"]] = a
        file.close()
        logger.debug(":loadAll: loaded %d airports" % (len(Airport._DB)))


    @staticmethod
    def find(icao: str):
        return Airport._DB[icao] if icao in Airport._DB else None


    @staticmethod
    def findIATA(iata: str):
        return Airport._DB_IATA[iata] if iata in Airport._DB_IATA else None


    def loadFromFile(self):
        return [False, "no load implemented"]


    def addAirline(self, airline, isHub: bool = False):
        self.airlines[airline.icao] = airline
        if isHub:
            self.addHub(airline)


    def addHub(self, airline):
        self.hub[airline.icao] = airline


# ################################@
# AIRPORT BASE
#
#
class AirportBase(Airport):
    """
    An AirportBase is a more complete version of an airport.
    It is used as the basis of a ManagedAirport and can be used for origin and destination airport
    if we use procedures.
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
        self.metar = None
        self.rops = {}  # runway(s) in operation if metar provided.

    def setAirspace(self, airspace):
        self.airspace = airspace

    def load(self):
        status = self.loadFromFile()
        if not status[0]:
            return status

        status = self.loadProcedures()
        if not status[0]:
            return status

        status = self.loadRunways()
        if not status[0]:
            return status

        status = self.loadParkings()
        if not status[0]:
            return status

        status = self.loadTaxiways()
        if not status[0]:
            return status

        status = self.loadServiceRoads()
        if not status[0]:
            return status

        status = self.loadPOIS()
        if not status[0]:
            return status

        return [True, "Airport::load loaded"]


    def loadFromFile(self):
        return [True, "no load implemented"]

    def loadGeometries(self, name):
        df = os.path.join(self.airport_base, "geometries", name)
        if os.path.exists(df):
            with open(df, "r") as fp:
                self.data = json.load(fp)
        else:
            logger.warning(":file: %s not found" % df)
            return [False, "GeoJSONAirport::loadGeometries file %s not found", df]
        return [True, "GeoJSONAirport::file %s loaded" % name]

    def loadProcedures(self):
        self.procedures = CIFP(self.icao)
        return [True, "XPAirport::loadProcedures: loaded"]

    def loadRunways(self):
        return [True, "no load implemented"]

    def loadTaxiways(self):
        return [True, "no load implemented"]

    def loadParkings(self):
        return [True, "no load implemented"]

    def loadServiceRoads(self):
        return [True, "no load implemented"]

    def loadPOIS(self):
        return [True, "no load implemented"]

    def setMETAR(self, metar: 'Metar'):
        if metar.metar is not None:
            self.metar = metar.metar
            logger.debug(":setMETAR: %s" % self.metar)
            if self.procedures is not None:
                # set which runways are usable
                self.rops = self.procedures.getOperationalRunways(self.metar.wind_dir.value())
        else:
            logger.debug(":setMETAR: no metar")

    def runwayIsWet(self):
        landing = 1.1
        if self.metar is not None:
            if self.metar.precip_1hr is not None:
                prec = self.metar.precip_1hr.value(units="CM")
                if prec > 0.5:
                    landing = 1.75
                elif prec > 0 or self.metar.precip_1hr.istrace():
                    landing = 1.4
        return landing

    def has_procedures(self) -> bool:
        return self.procedures is not None

    def getProcedure(self, flight: 'Flight', runway: str):
        logger.debug(":getProcedure: direction: %s" % type(flight).__name__)
        procs = self.procedures.STARS if type(flight).__name__ == 'Arrival' else self.procedures.SIDS
        validprocs = list(filter(lambda x: x.runway == runway.name, procs.values()))
        if len(validprocs) > 0:
            return random.choice(validprocs)
        logger.warning(":getProcedure: no procedure found for runway %s" % runway)
        return None

    def getOtherProcedure(self, flight: 'Flight', runway: str):
        logger.debug(":getOtherProcedure: direction: %s (TO BE REVERSED)" % type(flight).__name__)
        procs = self.procedures.SIDS if type(flight).__name__ == 'Arrival' else self.procedures.STARS
        validprocs = list(filter(lambda x: x.runway == runway.name, procs.values()))
        if len(validprocs) > 0:
            return random.choice(validprocs)
        logger.warning(":getOtherProcedure: no procedure found for runway %s" % runway)
        return None

    def getApproach(self, procedure: 'Procedure', runway: str):  # Procedure should be a STAR
        procs = self.procedures.APPCHS
        validappchs = list(filter(lambda x: x.runway == runway.name, procs.values()))
        if len(validappchs) > 0:
            return random.choice(validappchs)
        logger.warning(":getApproach: no aproach found for runway %s" % runway)
        return None

    def selectRunway(self, flight: 'Flight'):
        """
        Gets a valid runway for flight, depending on QFU, flight type (pax, cargo), destination, etc.

        :param      flight:  The flight
        :type       flight:  Flight

        :returns:   The runway.
        :rtype:     { return_type_description }
        """
        if len(self.rops) > 0:
            rwy = random.choice(list(self.rops.keys()))
            return self.procedures.RWYS[rwy]

        logger.warning(":getRunway: no qfu")
        rwy = random.choice(list(self.procedures.RWYS.keys()))  ## formally random.choice(list(self.procedures.RWYS)) is faster
        return self.procedures.RWYS[rwy]

    def getRamp(self, flight: 'Flight'):
        """
        Gets a valid ramp for flight depending on its attibutes.

        :param      flight:  The flight
        :type       flight:  Flight

        :returns:   The runway.
        :rtype:     { return_type_description }
        """
        ramp = random.choice(list(self.parkings))  ## formally random.choice(list(self.procedures.RWYS)) is faster
        return ramp
