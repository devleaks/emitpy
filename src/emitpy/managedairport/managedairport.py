"""
Assembly class to collect aerospace, managed airport, airport manager...
"""
import os
import logging
import json

import emitpy
from datetime import datetime

from emitpy.business import Airline, Company
from emitpy.aircraft import AircraftType, AircraftTypeWithPerformance
from emitpy.airport import Airport

# All base directories will be checked and created if non existent
from emitpy.constants import FEATPROP, AODB_DIRECTORIES
from emitpy.parameters import HOME_DIR, DATA_DIR, TEMP_DIR
from emitpy.parameters import CACHE_DIR, WEATHER_DIR
from emitpy.parameters import MANAGED_AIRPORT_DIR, MANAGED_AIRPORT_AODB, MANAGED_AIRPORT_CACHE

logger = logging.getLogger("ManagedAirport")

DEFAULT_AIRPORT_OPERATOR = "AIRPORT_OPERATOR"  # default value


class ManagedAirport:
    """
    Wrapper class to load all managed airport parts: Aerospace, Airport Manager, and Managed Airport itself.
    """

    def __init__(self, icao, app):
        self.icao = icao
        self._inited = False
        self._app = app  # context
        self.airport = None

        self.airac_cycle = None
        self.emitpy_version = emitpy.__version__
        self.last_updated = None

        self.operator = None
        self.timezone = None

        self.weather_engine = None

        self.setAirportDetails()

    def init(self, load_airways: bool = True):
        """
        Load entire managed airport data together with airport manager.
        """
        if self._inited:
            return (False, "ManagedAirport::init already inited")

        status = self.mkdirs(create=True)
        if not status[0]:
            return status

        # Now caching ManagedAirport with pickle (~ 100MB)
        logger.debug("loading managed airport..")

        self.airport = self._app._managedairport.new(cache=MANAGED_AIRPORT_CACHE, apt=self.getAirportDetails())
        logger.debug("..initializing managed airport..")
        self.timezone = self.airport.getTimezone()

        # Now caching Airspace with pickle (~ 100MB)
        logger.debug("..loading airspace..")
        airspace = self._app._aerospace.new(cache=CACHE_DIR, load_airways=load_airways, redis=self._app.redis)

        if not self._app._use_redis:  # load from data files
            logger.debug("..loading airlines..")
            Airline.loadAll(self.icao)
            Airline.loadFlightOperators(self.icao)
            logger.debug("..done")

            logger.debug("..loading aircrafts..")
            AircraftType.loadAll()
            AircraftTypeWithPerformance.loadAll()
            logger.debug("..done")

        logger.debug("..loading airport manager..")
        logger.debug("..creating airport operator..")
        operator = Company(orgId="Airport Operator", classId="Airport Operator", typeId="Airport Operator", name=self.operator)
        manager = self._app._airportmanager(icao=self.icao, operator=operator)
        ret = manager.load(self._app.redis)
        if not ret[0]:
            logger.error("..airport manager !** not loaded **!")
            return ret

        logger.debug("..setting managed airport resources..")

        self.airport.setAirspace(airspace)
        self.airport.setManager(manager)
        ret = manager.init(self.airport)  # passed to get runways and ramps
        if not ret[0]:
            logger.error("..airport manager !** not initialized **!")
            return ret

        # Setting up weather
        logger.debug("..setting up weather..")
        self.weather_engine = self._app._weather_engine.new(redis=self._app.redis)
        logger.debug("..updating weather of managed airport..")
        self.updateWeather()
        logger.debug("..done")

        self._inited = True

        # if self._app._use_redis:
        # logger.debug(json.dumps(self.airport.getSummary(), indent=2))

        return (True, "ManagedAirport::init done")

    def getAirportDetails(self):
        if self.operator is None:
            self.setAirportDetails()
            if self.operator is None:
                return {}
        return {
            "ICAO": self.icao,
            "IATA": self.iata,
            "name": self.name,
            "name_local": self.name,
            "city": self.city,
            "country": self.country,
            "regionName": self.region,
            "elevation": self.elevation,  # meters ASL
            "lat": self.latitude,
            "lon": self.longitude,
            "operator": self.operator,
        }

    def setAirportDetails(self):
        if self.operator is not None:  # can only set once...
            return

        this_airport = Airport.findICAO(self.icao, self._app.use_redis())
        if this_airport is not None:
            self.iata = this_airport.iata
            self.name = this_airport.display_name
            self.city = this_airport.getProp(FEATPROP.CITY)
            self.country = this_airport.getProp(FEATPROP.COUNTRY)
            self.region = this_airport.region
            self.latitude = this_airport.lat()
            self.longitude = this_airport.lon()
            self.elevation = this_airport.altitude()
            self.name = this_airport.display_name
            self.operator = DEFAULT_AIRPORT_OPERATOR
            logger.debug(f"setAirportDetails: found {self.icao}")
        else:
            self.operator = None
            logger.warning(f"setAirportDetails: {self.icao} not found")

    def setAirportOperator(self, operator):
        self.operator = operator

    def mkdirs(self, create: bool = True):
        """
        Check and creates directories necessary for managing this airport.
        """
        # Mandatory directories
        dirs = [HOME_DIR, DATA_DIR]
        ok = True
        for d in dirs:
            if not os.path.exists(d):
                ok = False
                logger.warning(f"directory {d} does not exist")
        if not ok:
            return (False, "ManagedAirport::mkdirs missing mandatory base directories")

        # Global directories
        dirs = [TEMP_DIR, CACHE_DIR, WEATHER_DIR, MANAGED_AIRPORT_DIR, MANAGED_AIRPORT_AODB, MANAGED_AIRPORT_CACHE]
        for d in dirs:
            if not os.path.exists(d):
                logger.warning(f"directory {d} does not exist")
                if create:
                    os.makedirs(d)
                    logger.info(f"created directory {d}")

        # Managed airport sub directories
        for sd in AODB_DIRECTORIES:
            d = os.path.join(MANAGED_AIRPORT_AODB, sd.value)
            if not os.path.exists(d):
                logger.warning(f"directory {d} does not exist")
                if create:
                    os.makedirs(d)
                    logger.info(f"created directory {d}")

        return (True, "ManagedAirport::init done")

    def updateWeather(self):
        """
        Update METAR data for managed airport.
        If self instance is loaded for a long time, this procedure should be called
        at regular interval. (It will, sometimes, be automatic (Thread).)
        (Let's dream, someday, it will load, parse and interpret TAF.)
        """
        self.airport.updateWeather(weather_engine=self.weather_engine)  # calls prepareRunways()

    def loadFromCache(self, dbid: int = 0):
        """
        Loads static and reference data for Managed Airport and Airport Manager from Redis datastore.

        :param      dbid:  The dbid
        :type       dbid:  int
        """
        pass
