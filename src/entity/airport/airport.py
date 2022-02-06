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

from metar import Metar

from ..graph import Graph
from ..geo import Location

from ..constants import AIRPORT_DATABASE
from ..parameters import DATA_DIR, LOAD_AIRWAYS
from ..utils import FT
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
        logger.debug(":loadAll: loaded %d airports" % len(Airport._DB))


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
        self.metar = None
        self.rops = {}  # runway(s) in operation if metar provided.

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

        status = self.loadPOIS()
        if not status[0]:
            return [False, status[1]]

        return [True, "Airport::load loaded"]


    def loadFromFile(self):
        return [False, "no load implemented"]

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
        return [False, "no load implemented"]

    def loadRunways(self):
        return [False, "no load implemented"]

    def loadTaxiways(self):
        return [False, "no load implemented"]

    def loadParkings(self):
        return [False, "no load implemented"]

    def loadServiceRoads(self):
        return [False, "no load implemented"]

    def loadPOIS(self):
        return [False, "no load implemented"]

    def setMETAR(self, metar: str):
        self.metar = Metar.Metar(metar)
        logger.debug(":setMETAR: %s" % self.metar)
        self._computeOperationalRunways()

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

    def _computeOperationalRunways(self):
        qfu = self.metar.wind_dir.value()
        max1 = qfu - 90
        if max1 < 0:
            max1 = max1 + 360
        max1 = int(max1/10)
        max2 = qfu + 90
        if max2 > 360:
            max2 = max2 - 360
        max2 = int(max2/10)
        if max1 > max2:
            max1, max2 = max2, max1

        # logger.debug(":_computeOperationalRunways: %f %d %d" % (qfu, max1, max2))
        if qfu > 90 and qfu < 270:
            for rwy in self.procedures.RWYS.keys():
                # logger.debug(":_computeOperationalRunways: %s %d" % (rwy, int(rwy[2:4])))
                rw = int(rwy[2:4])
                if rw >= max1 and rw < max2:
                    # logger.debug(":_computeOperationalRunways: added %s" % rwy)
                    self.rops[rwy] = self.procedures.RWYS[rwy]
        else:
            for rwy in self.procedures.RWYS.keys():
                # logger.debug(":_computeOperationalRunways: %s %d" % (rwy, int(rwy[2:4])))
                rw = int(rwy[2:4])
                if rw < max1 or rw >= max2:
                    # logger.debug(":_computeOperationalRunways: added %s" % rwy)
                    self.rops[rwy] = self.procedures.RWYS[rwy]

        if len(self.rops.keys()) == 0:
            logger.debug(":_computeOperationalRunways: could not find runway for operations")

        logger.info(":_computeOperationalRunways: wind direction is %f, runway in use: %s" % (qfu, self.rops.keys()))


    def getProcedure(self, flight: 'Flight', runway: str):
        logger.debug(":getProcedure: direction: %s" % type(flight).__name__)
        procs = self.procedures.STARS if type(flight).__name__ == 'Arrival' else self.procedures.SIDS
        validprocs = list(filter(lambda x: x.runway == runway.name, procs.values()))
        if len(validprocs) > 0:
            return random.choice(validprocs)
        logger.warning(":getProcedure: no procedure found for runway %s" % runway)
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
        rwy = random.choice(list(self.runways))  ## formally random.choice(list(self.procedures.RWYS)) is faster
        return self.procedures.RWYS["RW"+rwy]

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
