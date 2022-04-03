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
import operator

import geojson

from ..graph import Graph
from ..geo import Location

from ..airspace import CIFP
from ..constants import AIRPORT_DATABASE, FEATPROP
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
        self.display_name = None

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
                a.display_name = row["name"]
                Airport._DB[row["ident"]] = a
                Airport._DB_IATA[row["iata_code"]] = a
        file.close()
        logger.debug(f":loadAll: loaded {len(Airport._DB)} airports")


    @staticmethod
    def find(code: str):
        # Usually, ICAO codes are 5 letters "EBBR", IATA codes are 3 letter "BRU"
        if len(code) == 4:
            return Airport._DB[code] if code in Airport._DB else None
        return Airport._DB_IATA[code] if code in Airport._DB_IATA else None


    @staticmethod
    def findICAO(icao: str):
        return Airport._DB[icao] if icao in Airport._DB else None


    @staticmethod
    def findIATA(iata: str):
        return Airport._DB_IATA[iata] if iata in Airport._DB_IATA else None


    @staticmethod
    def getCombo():
        l = filter(lambda a: len(a.airlines) > 0, Airport._DB_IATA.values())
        return [(a.iata, a.display_name) for a in sorted(l, key=operator.attrgetter('display_name'))]


    def loadFromFile(self):
        return [False, "no load implemented"]


    def addAirline(self, airline, isHub: bool = False):
        self.airlines[airline.icao] = airline
        if isHub:
            self.addHub(airline)


    def addHub(self, airline):
        self.hub[airline.icao] = airline


    def getInfo(self):
        return {
            "icao": self.icao,
            "iata": self.iata,
            "name": self.getProp(FEATPROP.NAME.value),
            "city": self.getProp("city"),
            "country": self.getProp("country")
        }


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
        self.manager = None
        self.procedures = None
        self.taxiways = Graph()
        self.service_roads = Graph()
        self.runways = {}               # GeoJSON Features
        self.ramps = {}                 # GeoJSON Features
        self.service_destinations = {}  # GeoJSON Features
        self.metar = None
        self.operational_rwys = {}  # runway(s) in operation if metar provided, runways in here are RWY objects, not GeoJSON Feature.

    def setAirspace(self, airspace):
        self.airspace = airspace

    def setManager(self, manager):
        self.manager = manager

    def load(self):
        status = self.loadFromFile()
        if not status[0]:
            return status

        status = self.loadRunways()  # These are the GeoJSON features
        if not status[0]:
            return status

        status = self.loadProcedures()  # which includes runways that are RWY objects
        if not status[0]:
            return status

        status = self.loadRamps()
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
        # Loads GeoJSON file, returned dict has proper GeoJSON types,
        # ie. not 'dict' but 'FeatureCollection', 'Feature', 'Point', etc.
        df = os.path.join(self.airport_base, "geometries", name)
        if os.path.exists(df):
            with open(df, "r") as fp:
                self.data = geojson.load(fp)
        else:
            logger.warning(f":file: {df} not found")
            return [False, "GeoJSONAirport::loadGeometries file %s not found", df]
        return [True, f"GeoJSONAirport::file {name} loaded"]

    def loadProcedures(self):
        self.procedures = CIFP(self.icao)
        return [True, "XPAirport::loadProcedures: loaded"]

    def loadRunways(self):
        return [True, "no load implemented"]

    def loadTaxiways(self):
        return [True, "no load implemented"]

    def loadRamps(self):
        return [True, "no load implemented"]

    def loadServiceRoads(self):
        return [True, "no load implemented"]

    def loadPOIS(self):
        return [True, "no load implemented"]

    def getRampCombo(self):
        l = sorted(self.ramps.values(),key=lambda x: x.getProp("name"))
        a = [(a.getProp("name"), a.getProp("name")) for a in l]
        return a

    def getRunwayCombo(self):
        l = sorted(self.runways.values(),key=lambda x: x.getProp("name"))
        a = [(a.getProp("name"), "RW" + a.getProp("name")) for a in l]
        return a

    def setMETAR(self, metar: 'Metar'):
        if metar.metar is not None:
            self.metar = metar.metar
            logger.debug(f":setMETAR: {self.metar}")
            if self.procedures is not None:
                # set which runways are usable
                wind_dir = self.metar.wind_dir
                if wind_dir is None:  # wind dir is variable, any runway is fine
                    logger.debug(":setMETAR: no wind direction")
                    self.operational_rwys = self.procedures.getRunways()
                else:
                    logger.debug(f":setMETAR: wind direction {wind_dir.value():.1f}")
                    self.operational_rwys = self.procedures.getOperationalRunways(wind_dir.value())
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

    def has_sids(self) -> bool:
        return self.has_procedures() and len(self.procedures.SIDS) > 0

    def has_stars(self) -> bool:
        return self.has_procedures() and len(self.procedures.STARS) > 0

    def has_approaches(self) -> bool:
        return self.has_procedures() and len(self.procedures.APPCHS) > 0

    def has_rwys(self) -> bool:
        return self.has_procedures() and len(self.procedures.RWYS) > 0

    def has_proc(self, runway, all_procs):
        sel_procs = {}
        # Runway specific procs:
        if runway.name in all_procs:
            sel_procs.update(all_procs[runway.name])
            # logger.debug(":has_proc: added rwy specific %ss: %s: %s" % (procname, runway.name, all_procs[runway.name].keys()))

        # Procedures valid for "both" runways:
        both = runway.both()
        if both in all_procs:
            sel_procs.update(all_procs[both])
            # logger.debug(":has_proc: added both-rwys %ss: %s: %s" % (procname, both, all_procs[both].keys()))

        # Procedures valid for all runways:
        if "ALL" in all_procs:
            sel_procs.update(all_procs["ALL"])
            # logger.debug(":has_proc: added all-rwys %ss: %s" % (procname, all_procs["ALL"].keys()))

        return len(sel_procs) > 0

    def getProc(self, runway, all_procs, procname):
        sel_procs = {}
        # Runway specific procs:
        if runway.name in all_procs:
            sel_procs.update(all_procs[runway.name])
            logger.debug(f":getProc: added rwy specific {procname}s: {runway.name}: {all_procs[runway.name].keys()}")

        # Procedures valid for "both" runways:
        both = runway.both()
        if both in all_procs:
            sel_procs.update(all_procs[both])
            logger.debug(f":getProc: added both-rwys {procname}s: {both}: {all_procs[both].keys()}")

        # Procedures valid for all runways:
        if "ALL" in all_procs:
            sel_procs.update(all_procs["ALL"])
            logger.debug(f":getProc: added all-rwys {procname}s: {all_procs['ALL'].keys()}")

        if len(sel_procs) > 0:
            logger.debug(f":getProc: selected {procname}s for {runway.name}: {sel_procs.keys()}")
            ret = random.choice(list(sel_procs.values()))
            # logger.debug(":getProc: returning %s for %s: %s" % (procname, runway.name, ret.name))
            return ret

        logger.warning(f":getProc: no {procname} found for runway {runway.name}")
        return None

    def selectSID(self, runway: 'Runway'):
        # @todo: Need to be a lot more clever to find procedure.
        return self.getProc(runway, self.procedures.SIDS, "SID")

    def selectSTAR(self, runway: 'Runway'):
        # @todo: Need to be a lot more clever to find procedure.
        return self.getProc(runway, self.procedures.STARS, "STAR")

    def selectApproach(self, procedure: 'STAR', runway: 'Runway'):  # Procedure should be a STAR
        # @todo: Need to be a lot more clever to find procedure.
        return self.getProc(runway, self.procedures.APPCHS, "APPCH")

    def selectRWY(self, flight: 'Flight'):
        """
        Gets a valid runway for flight, depending on QFU, flight type (pax, cargo), destination, etc.

        :param      flight:  The flight
        :type       flight:  Flight

        :returns:   The runway.
        :rtype:     { return_type_description }
        """
        candidates = []
        if len(self.operational_rwys) > 0:
            for v in self.operational_rwys.values():
                if flight.is_departure():
                    if self.has_proc(v, self.procedures.SIDS):
                        candidates.append(v)
                else:
                    if self.has_proc(v, self.procedures.STARS) or self.has_proc(v, self.procedures.APPCHS) :
                        candidates.append(v)

        if len(candidates) == 0:
            logger.warning(":selectRunway: could not select runway")
            if len(self.operational_rwys) > 0:
                logger.warning(":selectRunway: choosing random operational runway")
                return random.choice(list(self.operational_rwys.values()))
            if len(self.procedures.RWYS) > 0:
                logger.warning(":selectRunway: choosing random runway")
                return random.choice(list(self.procedures.RWYS.values()))
            return None

        return random.choice(candidates)

    def getRunway(self, rwy):
        n = rwy.name.replace("RW", "")
        if n in self.runways.keys():
            return self.runways[n]
        logger.warning(f":getRunway: runway {n} not found")
        return None

    def getRWY(self, runway):
        n = "RW" + runway.getProp("name")
        if n in self.procedures.RWYS.keys():
            return self.procedures.RWYS[n]
        logger.warning(f":getRWY: RWY {n} not found")
        return None

    def selectRamp(self, flight: 'Flight'):
        """
        Gets a valid ramp for flight depending on its attibutes.

        :param      flight:  The flight
        :type       flight:  Flight

        :returns:   The runway.
        :rtype:     { return_type_description }
        """
        return random.choice(list(self.ramps.values()))

