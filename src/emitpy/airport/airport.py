"""
Different types of airports, depending on their status in the simulation.

- Airport: Simple, regular terminal.
- ManagedAirportBase: Augmented terminal location with additional information such as runways, procedures, etc.
- ManagedAirport: An ManagedAirportBase with yet additional information such as taxiway network, road service network, etc.
  for the study of airport ground operations.
"""
from __future__ import annotations

import os
import csv
import json
import logging
import pickle
import random
import operator
from abc import ABC, abstractmethod

from timezonefinder import TimezoneFinder
from zoneinfo import ZoneInfo
from datetime import datetime, timezone

from turfpy.measurement import distance, point_to_line_distance

from emitpy.graph import Graph, USAGE_TAG
from emitpy.geo import Location

from emitpy.airspace import CIFP, Metar, Terminal
from emitpy.constants import AIRPORT_DATABASE, FEATPROP, REDIS_PREFIX, REDIS_DATABASE, REDIS_LOVS, REDIS_DB
from emitpy.parameters import DATA_DIR, METAR_HISTORICAL
from emitpy.geo import FeatureWithProps, Ramp, Runway, cleanFeatures
from emitpy.utils import Timezone, FT, key_path, rejson

logger = logging.getLogger("Airport")


# ################################
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
        self.display_name = name

        self._rawdata = {}
        self.airlines = {}
        self.hub = {}

        self.tzname = None
        self.tzoffset = None
        self.timezone = None

        # this is the airway network representation of this airport
        self.terminal = Terminal(name=icao, lat=lat, lon=lon, alt=alt, iata=iata, longname=name, country=country, city=city)

    @staticmethod
    def loadAll():
        """
        Loads all known airports from a global airport list file.
        Currently, the data file used returns the follwing information:

        - id
        - ident
        - type
        - name
        - latitude_deg
        - longitude_deg
        - elevation_ft
        - continent
        - iso_country
        - iso_region
        - municipality
        - scheduled_service
        - gps_code
        - iata_code
        - local_code
        - home_link
        - wikipedia_link
        - keywords

        """
        filename = os.path.join(DATA_DIR, AIRPORT_DATABASE, "airports.csv")
        file = open(filename, "r")
        csvdata = csv.DictReader(file)
        for row in csvdata:
            lat = float(row["latitude_deg"]) if row["latitude_deg"] != "" else 0.0
            lon = float(row["longitude_deg"]) if row["longitude_deg"] != "" else 0.0
            if lat != 0.0 or lon != 0.0:
                alt = 0
                if "elevation_ft" in row and row["elevation_ft"]  != "":
                    alt = float(row["elevation_ft"])*FT
                apt = Airport(icao=row["ident"],
                              iata=row["iata_code"],
                              name=row["name"],
                              city=row["municipality"],
                              country=row["iso_country"],
                              region=row["iso_region"],
                              lat=lat,
                              lon=lon,
                              alt=alt)
                apt.display_name = row["name"]
                Airport._DB[row["ident"]] = apt
                Airport._DB_IATA[row["iata_code"]] = apt
            else:
                logger.warning("invalid airport data %s.", row)

        file.close()
        logger.debug(f"loaded {len(Airport._DB)} airports")


    @staticmethod
    def find(code: str, redis = None):
        """
        Finds an airport by its IATA (always 3 letter) or ICAO (2-4, often 4 letter) code.

        :param      code:  The code
        :type       code:  str
        """
        if redis is not None:
            if len(code) == 4:
                k = key_path(key_path(REDIS_PREFIX.AIRPORTS.value, REDIS_PREFIX.ICAO.value))
            else:
                k = key_path(key_path(REDIS_PREFIX.AIRPORTS.value, REDIS_PREFIX.IATA.value))
            ac = rejson(redis=redis, key=k, db=REDIS_DB.REF.value, path=f".{code}")
            if ac is not None:
                return Airport.fromFeature(info=ac)
            else:
                logger.warning(f"Airport::find: no such key {k}")
                return None

        return Airport.findICAO(code) if len(code) == 4 else Airport.findIATA(code)


    @staticmethod
    def findICAO(icao: str, redis = None):
        """
        Finds an Airport be its ICAO code.

        :param      icao:  The icao
        :type       icao:  str
        """
        if redis is not None:
            k = key_path(REDIS_PREFIX.AIRPORTS.value, REDIS_PREFIX.ICAO.value, icao[0:2], icao)
            ac = rejson(redis=redis, key=k, db=REDIS_DB.REF.value)
            # k = key_path(REDIS_PREFIX.AIRPORTS.value, REDIS_PREFIX.ICAO.value)
            # ac = rejson(redis=redis, key=k, db=REDIS_DB.REF.value, path=f".{icao}")
            if ac is not None:
                return Airport.fromInfo(info=ac)
            else:
                logger.warning(f"no such key {k}")
        else:
            if len(Airport._DB) == 0:
                Airport.loadAll()
            return Airport._DB[icao] if icao in Airport._DB else None
        return None


    @staticmethod
    def findIATA(iata: str, redis = None):
        """
        Finds an Airport be its IATA code.

        :param      icao:  The icao
        :type       icao:  str
        """
        if redis is not None:
            k = key_path(REDIS_PREFIX.AIRPORTS.value, REDIS_PREFIX.IATA.value)
            ac = rejson(redis=redis, key=k, db=REDIS_DB.REF.value, path=f".{iata}")
            if ac is not None:
                return Airport.fromFeature(info=ac)
            else:
                logger.warning(f"no such key {k}")
        else:
            if len(Airport._DB_IATA) == 0:
                Airport.loadAll()
            return Airport._DB_IATA[iata] if iata in Airport._DB_IATA else None
        return None


    @staticmethod
    def getCombo(redis = None):
        """
        Returns a list of pairs (code, description) ssorted by description.
        """
        if redis is not None:
            k = key_path(REDIS_DATABASE.LOVS.value, REDIS_LOVS.AIRPORTS.value)
            # return rejson(redis=redis, key=k, db=REDIS_DB.REF.value)
            temp = rejson(redis=redis, key=k, db=REDIS_DB.REF.value)
            return {"airports": [{"iata": k, "name": v} for k,v in temp.items()]}

        l = filter(lambda a: len(a.airlines) > 0, Airport._DB_IATA.values())
        m = [(a.iata, a.display_name) for a in sorted(l, key=operator.attrgetter('display_name'))]
        return m


    @classmethod
    def fromFeature(cls, info):
        """
        Build and Airport instance from properties extracted for a GeoJSON Feature.

        :param      cls:   The cls
        :type       cls:   { type_description }
        :param      info:  The information
        :type       info:  { type_description }
        """
        # logger.debug(f"{json.dumps(info, indent=2)}")
        return Airport(icao=info["icao"],
                       iata=info["iata"],
                       name=info["properties"]["name"],
                       city=info["properties"]["city"],
                       country=info["properties"]["country"],
                       region=info["region"],
                       lat=float(info["geometry"]["coordinates"][1]),
                       lon=float(info["geometry"]["coordinates"][0]),
                       alt=float(info["geometry"]["coordinates"][2] if len(info["geometry"]["coordinates"])>2 else None))

    @classmethod
    def fromInfo(cls, info):
        """
        Builds an Airport instance from the dictionary returned by airport.getInfo() function.

        :param      cls:   The cls
        :type       cls:   { type_description }
        :param      info:  The information
        :type       info:  { type_description }
        """
        # logger.debug(f"{json.dumps(info, indent=2)}")
        return Airport(icao=info["icao"],
                       iata=info["iata"],
                       name=info["name"],
                       city=info["city"],
                       country=info["country"],
                       region=info["iso_region"],
                       lat=info["lat"],
                       lon=info["lon"],
                       alt=info["alt"])

    def __str__(self):
        return f"{self['properties']['name']}, {self['properties']['city']}, {self['properties']['country']} ({self.iata}, {self.icao})"


    def getId(self):
        return self.terminal.getId()


    def getTerminal(self):
        return self.terminal


    def loadFromFile(self):
        """
        Loads individual airport data.
        """
        return [False, "no load implemented"]


    def addAirline(self, airline, isHub: bool = False):
        """
        Adds an airline as an operator at that airport.

        :param      airline:  The airline
        :type       airline:  { type_description }
        :param      isHub:    Indicates if hub
        :type       isHub:    bool
        """
        self.airlines[airline.icao] = airline
        if isHub:
            self.addHub(airline)


    def addHub(self, airline):
        """
        Adds an airline as a hub operator at that airport.

        :param      airline:  The airline
        :type       airline:  { type_description }
        :param      isHub:    Indicates if hub
        :type       isHub:    bool
        """
        self.hub[airline.icao] = airline


    def getInfo(self) -> dict:
        """
        Returns airport information.
        """
        return {
            "icao": self.icao,
            "iata": self.iata,
            "name": self.getProp(FEATPROP.NAME.value),
            "city": self.getProp(FEATPROP.CITY.value),
            "country": self.getProp(FEATPROP.COUNTRY.value),
            "iso_region": self.region,
            "lat": self["geometry"]["coordinates"][1],
            "lon": self["geometry"]["coordinates"][0],
            "alt": self.altitude()
        }


    def getKey(self):
        return self.icao


    def miles(self, airport):
        """
        Returns the distance, in nautical miles, from the current (managed) airport to the supplied airport.
        Used to compute bonus milage.

        :param      airport:  The airport
        :type       airport:  { type_description }
        """
        return distance(self, airport)


    def save(self, base, redis):
        """
        Saves airport data to cache.

        :param      base:   The base
        :type       base:   { type_description }
        :param      redis:  The redis
        :type       redis:  { type_description }
        """
        if redis is not None:
            redis.delete(key_path(base, self.icao[0:2], self.getKey()))
            # redis.set(key_path(base, self.icao[0:2], self.getKey()), json.dumps(self.getInfo()))
            redis.json().set(key_path(base, self.icao[0:2], self.getKey()), "$", self.getInfo())


    def getTimezone(self):
        """
        Build a python datetime tzinfo object for the airport local timezone.
        Since python does not have a reference to all timezone, we rely on:
        - pytz, a python implementation of  (at https://pythonhosted.org/pytz/, https://github.com/stub42/pytz)
        - timezonefinder, a python package that finds the timezone of a (lat,lon) pair (https://github.com/jannikmi/timezonefinder).
        """
        if self.tzoffset is not None and self.tzname is not None:
            self.timezone = Timezone(offset=self.tzoffset, name=self.tzname)
            logger.debug("timezone set from offset/name")
        elif self.lat() is not None and self.lon() is not None:
            tf = TimezoneFinder()
            tzname = tf.timezone_at(lng=self.lon(), lat=self.lat())
            if tzname is not None:
                tzinfo = ZoneInfo(tzname)
                if tzinfo is not None:
                    self.tzname = tzname
                    self.tzoffset = round(datetime.now(tz=tzinfo).utcoffset().seconds / 3600, 1)
                    # self.timezone = tzinfo  # is 100% correct too
                    self.timezone = Timezone(offset=self.tzoffset, name=self.tzname)
                    logger.debug(f"timezone set from TimezoneFinder ({tzname})")
                else:
                    logger.error("ZoneInfo timezone not found")
            else:
                logger.error("TimezoneFinder timezone not found")
        else:
            logger.error("cannot set airport timezone")

        return self.timezone


    def update_metar(self, moment: str = None, redis = None):
        """
        Update METAR data for managed airport.
        If self instance is loaded for a long time, this procedure should be called
        at regular interval. (It will, sometimes, be automatic (Thread).)
        (Let's dream, someday, it will load, parse and interpret TAF.)
        """

        # if moment is not None and METAR_HISTORICAL:  # issues with web site to fetch historical metar.
        #     logger.debug(f"..historical.. ({scheduled})")
        #     remote_metar = Metar.new(icao=remote_apt.icao, redis=self.redis, method="MetarHistorical")
        #     remote_metar.setDatetime(moment=scheduled_dt)
        #     if not remote_metar.hasMetar():  # couldn't fetch historical, use current
        #         remote_metar = Metar.new(icao=remote_apt.icao, redis=self.redis)

        logger.debug("collecting METAR..")
        # Prepare airport for each movement
        metar = Metar.new(icao=self.icao, redis=redis)
        self.setMETAR(metar=metar)  # calls prepareRunways()
        logger.debug("..done")


# ################################
# AIRPORT + FLIGHT PROCEDURES
#
#
class AirportWithProcedures(Airport):
    """
    An AirportWithProcedures is an airport with CIFP procedures.
    AirportWithProcedures can be used as departure and/or arrival airport in flight plan.
    AirportWithProcedures also is the parent of BaseAirport.
    """

    def __init__(self, icao: str, iata: str, name: str, city: str, country: str, region: str, lat: float, lon: float, alt: float):
        Airport.__init__(self, icao=icao, iata=iata, name=name, city=city, country=country, region=region, lat=lat, lon=lon, alt=alt)
        self.procedures = None
        self.metar = None
        self.operational_rwys = {}  # runway(s) in operation if metar provided, runways in here are RWY objects, not GeoJSON Feature.


    @classmethod
    def new(cls, apt: Airport):
        base = cls(icao=apt.icao,
                   iata=apt.iata,
                   name=apt["properties"]["name"],
                   city=apt["properties"]["city"],
                   country=apt["properties"]["country"],
                   region=apt.region,
                   lat=apt["geometry"]["coordinates"][1],
                   lon=apt["geometry"]["coordinates"][0],
                   alt=apt["geometry"]["coordinates"][2] if len(apt["geometry"]["coordinates"]) > 2 else None)
        ret = base.load()
        if not ret[0]:
            logger.warning(f"could not load airport with procedures: {ret}")
        return base

    def getInfo(self):
        base = super().getInfo()
        if base is not None:
            base["procedures"] = self.procedures.getInfo()
        return base
        # return {
        #     "airport": super().getInfo(),
        #     "procedures": self.procedures.getInfo()
        # }


    def load(self):
        """
        Load ManagedAirportBase data from files.
        """
        return self.loadProcedures()  # which includes runways that are RWY objects


    def loadProcedures(self):
        """
        Loads CIFP procedures for airport if avaialble.

        :returns:   { description_of_the_return_value }
        :rtype:     { return_type_description }
        """
        self.procedures = CIFP(self.icao)
        return [True, "XPAirport::loadProcedures: loaded"]


    def has_procedures(self) -> bool:
        """
        Determines if procedures avaivable for airport.

        :returns:   True if procedures, False otherwise.
        :rtype:     bool
        """
        return self.procedures is not None

    def has_sids(self) -> bool:
        """
        Determines if SIDs avaivable for airport.

        :returns:   True if sids, False otherwise.
        :rtype:     bool
        """
        return self.has_procedures() and len(self.procedures.SIDS) > 0

    def has_stars(self) -> bool:
        """
        Determines if STARs avaivable for airport.

        :returns:   True if sids, False otherwise.
        :rtype:     bool
        """
        return self.has_procedures() and len(self.procedures.STARS) > 0

    def has_approaches(self) -> bool:
        """
        Determines if APPCHs avaivable for airport in CIFP procedures.

        :returns:   True if sids, False otherwise.
        :rtype:     bool
        """
        return self.has_procedures() and len(self.procedures.APPCHS) > 0

    def has_rwys(self) -> bool:
        """
        Determines if RWYs avaivable for airport in CIFP procedures.

        :returns:   True if sids, False otherwise.
        :rtype:     bool
        """
        return self.has_procedures() and len(self.procedures.RWYS) > 0

    def has_proc(self, runway, all_procs):
        """
        Common procedure test function.

        :param      runway:     The runway
        :type       runway:     { type_description }
        :param      all_procs:  All procs
        :type       all_procs:  { type_description }

        :returns:   True if proc, False otherwise.
        :rtype:     bool
        """
        sel_procs = {}
        # Runway specific procs:
        if runway.name in all_procs:
            sel_procs.update(all_procs[runway.name])
            # logger.debug("added rwy specific %ss: %s: %s" % (procname, runway.name, all_procs[runway.name].keys()))

        # Procedures valid for "both" runways:
        both = runway.both()
        if both in all_procs:
            sel_procs.update(all_procs[both])
            # logger.debug("added both-rwys %ss: %s: %s" % (procname, both, all_procs[both].keys()))

        # Procedures valid for all runways:
        if "ALL" in all_procs:
            sel_procs.update(all_procs["ALL"])
            # logger.debug("added all-rwys %ss: %s" % (procname, all_procs["ALL"].keys()))

        return len(sel_procs) > 0

    def getProc(self, runway, all_procs, procname):
        """
        Gets a procedure based in runway and procedure name.

        :param      runway:     The runway
        :type       runway:     { type_description }
        :param      all_procs:  All procs
        :type       all_procs:  { type_description }
        :param      procname:   The procname
        :type       procname:   { type_description }

        :returns:   The proc.
        :rtype:     { return_type_description }
        """
        sel_procs = {}
        # Runway specific procs:
        if runway.name in all_procs:
            sel_procs.update(all_procs[runway.name])
            logger.debug(f"added rwy specific {procname}s: {runway.name}: {all_procs[runway.name].keys()}")

        # Procedures valid for "both" runways:
        both = runway.both()
        if both in all_procs:
            sel_procs.update(all_procs[both])
            logger.debug(f"added both-rwys {procname}s: {both}: {all_procs[both].keys()}")

        # Procedures valid for all runways:
        if "ALL" in all_procs:
            sel_procs.update(all_procs["ALL"])
            logger.debug(f"added all-rwys {procname}s: {all_procs['ALL'].keys()}")

        if len(sel_procs) > 0:
            logger.debug(f"selected {procname}s for {runway.name}: {sel_procs.keys()}")
            ret = random.choice(list(sel_procs.values()))
            # logger.debug("returning %s for %s: %s" % (procname, runway.name, ret.name))
            return ret

        logger.warning(f"no {procname} found for runway {runway.name}")
        return None

    def selectSID(self, runway: 'Runway'):
        """
        Randomly select a SID for supplied runway.
        @todo: Need to be a lot more clever to find procedure.

        :param      runway:  The runway
        :type       runway:  { type_description }

        :returns:   { description_of_the_return_value }
        :rtype:     { return_type_description }
        """
        return self.getProc(runway, self.procedures.SIDS, "SID")

    def selectSTAR(self, runway: 'Runway'):
        """
        Randomly select a STAR for supplied runway.
        @todo: Need to be a lot more clever to find procedure.

        :param      runway:  The runway
        :type       runway:  { type_description }

        :returns:   { description_of_the_return_value }
        :rtype:     { return_type_description }
        """
        return self.getProc(runway, self.procedures.STARS, "STAR")

    def selectApproach(self, procedure: 'STAR', runway: 'Runway'):  # Procedure should be a STAR
        """
        Randomly select an APPCH for supplied runway and STAR.
        @todo: Need to be a lot more clever to find procedure.

        :param      runway:  The runway
        :type       runway:  { type_description }

        :returns:   { description_of_the_return_value }
        :rtype:     { return_type_description }
        """
        # @todo: Need to be a lot more clever to find procedure.
        return self.getProc(runway, self.procedures.APPCHS, "APPCH")

    def getRWY(self, runway):
        """
        Gets the RWY procedure instance for runway.

        :param      rwy:  The rwy
        :type       rwy:  { type_description }

        :returns:   The runway.
        :rtype:     { return_type_description }
        """
        n = "RW" + runway.getName()
        if n in self.procedures.RWYS.keys():
            return self.procedures.RWYS[n]
        logger.warning(f"RWY {n} not found")
        return None

    def setMETAR(self, metar: "Metar"):
        """
        Set METAR at airport. Triggers computation of operational runways depending on wind direction.

        :param      metar:  The metar
        :type       metar:  { type_description }

        :returns:   { description_of_the_return_value }
        :rtype:     { return_type_description }
        """
        if metar is not None:
            self.metar = metar
            logger.debug(f"{metar.getInfo()}")
            logger.debug(f"ATMAP: {metar.getAtmap()}")
            if self.procedures is not None:
                # set which runways are usable
                wind_dir = self.metar.getWindDirection()
                if wind_dir is None:  # wind dir is variable, any runway is fine
                    logger.debug("no wind direction")
                    self.operational_rwys = self.procedures.getRunways()
                else:
                    logger.debug(f"wind direction {wind_dir.value():.1f}")
                    self.operational_rwys = self.procedures.getOperationalRunways(wind_dir.value())
        else:
            self.operational_rwys = self.procedures.getRunways()
            logger.debug("no metar, using all runways")

    def selectRWY(self, flight: 'Flight'):
        """
        Selects a valid runway for flight, depending on QFU, flight type (pax, cargo), destination, etc.

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
            logger.warning("could not select runway")
            if len(self.operational_rwys) > 0:
                logger.warning("choosing random operational runway")
                return random.choice(list(self.operational_rwys.values()))
            if len(self.procedures.RWYS) > 0:
                logger.warning("choosing random runway")
                return random.choice(list(self.procedures.RWYS.values()))
            return None

        return random.choice(candidates)

    def runwayIsWet(self):
        """
        Artificially lengthen the landing distance based on amount of water on the ground.
        Amount of water is supplied by METAR in cm/hour.

        :returns:   { description_of_the_return_value }
        :rtype:     { return_type_description }
        """
        landing = 1.1
        if self.metar is not None:
            prec = self.metar.getPrecipitation()
            if prec > 0.5:
                landing = 1.75
            elif prec > 0:
                landing = 1.4
        return landing


# ################################
# AIRPORT BASE
#
#
class ManagedAirportBase(AirportWithProcedures):
    """
    An ManagedAirportBase the abstract class of a ManagedAirport. It defines all data and procedures
    necessary for the ManagedAirport but does not implement them.
    There are numerous ways to define a ManagedAirport and find necessary data.
    The loading of ManagedAirport data in performed in implementation specific ManagedAirport,
    collecting data from X-Plane, OSM or user-provided GeoJSON files for example, or
    any combination of the above providers.
    """

    def __init__(self, icao: str, iata: str, name: str, city: str, country: str, region: str, lat: float, lon: float, alt: float):
        AirportWithProcedures.__init__(self, icao=icao, iata=iata, name=name, city=city, country=country, region=region, lat=lat, lon=lon, alt=alt)
        self.airspace = None
        self.manager = None
        self.taxiways = Graph()
        self.service_roads = Graph()
        self.runways = {}               # GeoJSON Features
        self.ramps = {}                 # GeoJSON Features

        self.runways_in_use = []

        self.aeroway_pois = None
        self.service_pois = None
        self.check_pois = {}


    @classmethod
    def new(cls, cache, apt):
        airport = None
        airport_cache = os.path.join(cache, "airport.pickle")
        if os.path.exists(airport_cache):
            logger.debug(f"loading managed airport from pickle.. ({airport_cache})")
            with open(airport_cache, "rb") as fp:
                airport = pickle.load(fp)
            logger.debug("..done")
        else:
            logger.debug("creating managed airport..")
            airport = cls(
                icao=apt["ICAO"],
                iata=apt["IATA"],
                name=apt["name"],
                city=apt["city"],
                country=apt["country"],
                region=apt["regionName"],
                lat=apt["lat"],
                lon=apt["lon"],
                alt=apt["elevation"])
            logger.debug("..loading managed airport..")
            ret = airport.load()
            if not ret[0]:
                logger.error("..managed airport **not loaded!**")
                return ret
            logger.debug("..pickling airport..")
            with open(airport_cache, "wb") as fp:
                pickle.dump(airport, fp)
            logger.debug("..done")
        return airport


    def setAirspace(self, airspace):
        """
        Set airport airspace definition.

        :param      airspace:  The airspace
        :type       airspace:  { type_description }
        """
        self.airspace = airspace

    def setManager(self, manager):
        """
        Set AirportManager instance for commercial services.

        :param      manager:  The manager
        :type       manager:  { type_description }
        """
        self.manager = manager

    def getInfo(self):
        base = super().getInfo()
        if base is not None:
            base["info_source"] = type(self).__name__
        return base
        # return {
        #     "airport": super().getInfo(),
        #     "procedures": self.procedures.getInfo()
        # }

    def getSummary(self):
        base = self.getInfo()
        base["procedures"] = self.procedures.getInfo()
        base["runways"] = list(self.runways.keys())
        base["taxiway-network"] = (len(self.taxiways.vert_dict.keys()), len(self.taxiways.edges_arr))
        base["ramps"] = list(self.ramps.keys())
        base["aeroways-pois"] = list(self.aeroway_pois.keys())
        base["serviceroad-network"] = (len(self.service_roads.vert_dict.keys()), len(self.service_roads.edges_arr))
        base["service-pois"] = list(self.service_pois.keys())
        base["check-pois"] = list(self.check_pois.keys())
        return base

    def load(self):
        """
        Load ManagedAirportBase data from files.
        """
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
        """
        Load file at self.filename and place content in self.data.

        :returns:   { description_of_the_return_value }
        :rtype:     { return_type_description }
        """
        return [True, "no load implemented"]

    def loadGeometries(self, name):
        """
        Loads GeoJSON json file. GeoJSON features are immediately converted into FeatureWithProps Features.

        :param      name:  The name
        :type       name:  { type_description }

        :returns:   { description_of_the_return_value }
        :rtype:     { return_type_description }
        """
        # Loads GeoJSON file, returned dict has proper GeoJSON types,
        # ie. not 'dict' but 'FeatureCollection', 'Feature', 'Point', etc.
        self.data = None
        df = os.path.join(self.airport_base, "geometries", name)
        if os.path.exists(df):
            with open(df, "r") as fp:
                self.data = json.load(fp)
                if self.data is not None and self.data["features"] is not None:
                    self.data["features"] = FeatureWithProps.betterFeatures(self.data["features"])
            return [True, f"GeoJSONAirport::file {name} loaded"]
        logger.warning(f"{df} not found")
        return [False, "GeoJSONAirport::loadGeometries file %s not found", df]

    @abstractmethod
    def loadRunways(self):
        """
        Loads runways.

        :returns:   { description_of_the_return_value }
        :rtype:     { return_type_description }
        """
        return [True, "no load implemented"]

    @abstractmethod
    def loadTaxiways(self):
        """
        Loads network of taxiways. Should be a topology.

        :returns:   { description_of_the_return_value }
        :rtype:     { return_type_description }
        """
        return [True, "no load implemented"]

    @abstractmethod
    def loadRamps(self):
        """
        Loads ramps at airport. All ramp types (parking, gate, jetways, tie-down...) are loaded.
        A Ramp() is a GeoJSON Feature<Point> with an orientation and GeoJSON<Polygon> feature attached to it.

        :returns:   { description_of_the_return_value }
        :rtype:     { return_type_description }
        """
        return [True, "no load implemented"]

    @abstractmethod
    def loadServiceRoads(self):
        """
        Loads service roads network. Should be a topology.

        :returns:   { description_of_the_return_value }
        :rtype:     { return_type_description }
        """
        return [True, "no load implemented"]

    @abstractmethod
    def loadPOIS(self):
        """
        Loads a all Points of Interest at airport, including:
        -

        :returns:   { description_of_the_return_value }
        :rtype:     { return_type_description }
        """
        return [True, "no load implemented"]

    def getRampCombo(self):
        """
        Gets list of (code, description) pairs for all ramps.

        :returns:   The ramp combo.
        :rtype:     { return_type_description }
        """
        l = sorted(self.ramps.values(),key=lambda x: x.getName())
        # a = [(a.getName(), a.getName()) for a in l]
        # return a
        a = [{"name": a.getName(), "id": a.getName()} for a in l]
        return {"ramps": a}


    def getRunwayCombo(self):
        """
        Gets list of (code, description) pairs for runways.

        :returns:   The runway combo.
        :rtype:     { return_type_description }
        """
        l = sorted(self.runways.values(),key=lambda x: x.getName())
        a = [(a.getName(), "RW" + a.getName()) for a in l]
        return a

    def setRunwaysInUse(self, runways):
        if type(runways) in [list, tuple]:
            self.runways_in_use = runways
        elif type(runways) == Runway:
            if runways not in self.runways_in_use:
                self.runways_in_use.append(runways)
        elif runways == str:
            rwy = self.getRunway(runways)
            if rwy is not None:
                self.setRunwaysInUse(rwy)

    def getRunway(self, rwy: str) -> Runway:
        """
        Gets the Runway GeoJSON instance for a RWY procedure instance.

        :param      rwy:  The rwy
        :type       rwy:  { type_description }

        :returns:   The runway.
        :rtype:     { return_type_description }
        """
        n = rwy.name.replace("RW", "")
        if n in self.runways.keys():
            return self.runways[n]
        logger.warning(f"runway {n} not found")
        return None


    def getRunways(self):
        """
        Utility function to get all Runway's for resource usage.

        :returns:   The runways.
        :rtype:     { return_type_description }
        """
        return self.runways


    def getRamps(self):
        """
        Utility function to get all Ramp's for resource usage.

        :returns:   The ramps.
        :rtype:     { return_type_description }
        """
        return self.ramps


    def selectRamp(self, flight: 'Flight') -> Ramp:
        """
        Gets a valid ramp for flight depending on its attibutes.

        :param      flight:  The flight
        :type       flight:  Flight

        :returns:   The runway.
        :rtype:     { return_type_description }
        """
        return random.choice(list(self.ramps.values()))


    def pairRunways(self):
        """
        { function_description }
        """
        if len(self.runways) == 2:
            rwk = list(self.runways.keys())
            self.runways[rwk[0]].end, self.runways[rwk[1]].end = self.runways[rwk[1]], self.runways[rwk[0]]
            logger.debug(f"{self.icao}: {self.runways[rwk[0]].name} and {self.runways[rwk[1]].name} paired")
        else:
            logger.debug(f"{self.icao}: pairing {self.runways.keys()}")
            for k, r in self.runways.items():
                if r.end is None:
                    rh = int(k[0:2])
                    ri = rh + 18
                    if ri > 36:
                        ri = ri - 36
                    rl = k[-1]  # {L|R|C|<SPC>}
                    rw = "%02d" % ri
                    if rl == "L":
                        rw = rw + "R"
                    elif rl == "R":
                        rw = rw + "L"
                    elif rl == "C":
                        rw = rw + "C"
                    # elif rl == " ":
                    #     rw = rw
                    # else:
                    #     rw = rw
                    if rw in self.runways.keys():
                        r.end = self.runways[rw]
                        self.runways[rw].end = r
                        uuid = k+"-"+rw if k < rw else rw+"-"+k
                        r.uuid = uuid
                        r.end.uuid = uuid
                        logger.debug(f"{self.icao}: {r.getProp(FEATPROP.NAME.value)} and {rw} paired as {uuid}")
                    else:
                        logger.warning(f"{self.icao}: {rw} ont found to pair {r.getProp(FEATPROP.NAME.value)}")


    def findRunwayExits(self):
        fc = {}
        for rwy, runway in self.runways.items():
            width = float(runway["properties"]["width"]) / 1000  # meters
            line = FeatureWithProps(geometry=runway["properties"]["line"])
            cnt = 0
            for k, v in self.taxiways.vert_dict.items():
                d = point_to_line_distance(v, line)
                if d < width:
                    name = f"runway-exit:RW{rwy}:{cnt}"
                    fc[name] = FeatureWithProps(id=name, geometry=v["geometry"], properties={
                        "poi-type": "runway-exit",
                        "runway": "RW"+rwy,
                        "name": str(cnt)
                    })
                    cnt = cnt + 1
            logger.debug(f"{self.icao}: {rwy} found {cnt} exits")

        self.aeroway_pois = fc
        # with open("out.geojson", "w") as fp:
        #     json.dump(FeatureCollection(features=cleanFeatures(fc)), fp)
