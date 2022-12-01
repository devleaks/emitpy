# Assembly class to collect airport, airport manager, airspace...
import logging
import pickle
import os

from timezonefinder import TimezoneFinder
from zoneinfo import ZoneInfo

from emitpy.airspace import XPAirspace, Metar
from emitpy.business import Airline, Company
from emitpy.aircraft import AircraftType, AircraftPerformance
from emitpy.airport import Airport, XPAirport
from emitpy.business import AirportManager
from emitpy.utils import Timezone

# All base directories will be checked and created if non existent
from emitpy.parameters import HOME_DIR, DATA_DIR, TEMP_DIR
from emitpy.parameters import CACHE_DIR, METAR_DIR
from emitpy.parameters import MANAGED_AIRPORT_DIR, MANAGED_AIRPORT_AODB, MANAGED_AIRPORT_CACHE

logger = logging.getLogger("ManagedAirport")


class ManagedAirport:
    """
    Wrapper class to load all managed airport parts.
    """

    def __init__(self, airport, app):
        self._this_airport = airport  # simple dict
        self._inited = False
        self._app = app  # context
        self.airport = None
        self.timezone = None

        self.setTimezone()


    def init(self, load_airways: bool = True):
        """
        Load entire managed airport data together with airport manager.
        """
        if self._inited:
            return (False, "ManagedAirport::init already inited")

        status = self.mkdirs(create=True)
        if not status[0]:
            return status

        # Now caching Airspace with pickle (~ 100MB)
        airspace_cache = os.path.join(MANAGED_AIRPORT_CACHE, "airspace.pickle")
        if os.path.exists(airspace_cache):
            logger.debug("loading airspace from pickle..")
            with open(airspace_cache, "rb") as fp:
                airspace = pickle.load(fp)
            logger.debug("..done")
        else:
            airspace = XPAirspace(load_airways=load_airways)
            logger.debug("loading airspace..")
            ret = airspace.load(self._app.redis)
            if not ret[0]:
                logger.warning("Airspace not loaded")
                return ret
            logger.debug("..pickling airspace..")
            with open(airspace_cache, "wb") as fp:
                pickle.dump(airspace, fp)
            logger.debug("..done")

        if self._app.redis is None:  # load from data files

            logger.debug("loading airport..")
            Airport.loadAll()
            logger.debug("..done")

            logger.debug("loading airlines..")
            Airline.loadAll()
            logger.debug("..done")

            logger.debug("loading aircrafts..")
            AircraftType.loadAll()
            AircraftPerformance.loadAll()
            logger.debug("..done")

        logger.debug("loading managed airport..")

        logger.debug("..loading airport manager..")
        logger.debug("..creating airport operator..")
        operator = Company(orgId="Airport Operator",
                           classId="Airport Operator",
                           typeId="Airport Operator",
                           name=self._this_airport["operator"])
        manager = AirportManager(icao=self._this_airport["ICAO"], operator=operator, app=self._app)
        ret = manager.load(self._app.redis)
        if not ret[0]:
            logger.warning("Airport manager not loaded")
            return ret

        # Now caching ManagedAirport with pickle (~ 100MB)
        airport_cache = os.path.join(MANAGED_AIRPORT_CACHE, "airport.pickle")
        if os.path.exists(airport_cache):
            logger.debug("loading managed airport from pickle..")
            with open(airport_cache, "rb") as fp:
                self.airport = pickle.load(fp)
            logger.debug("..done")
        else:
            logger.debug("..loading managed airport..")
            self.airport = XPAirport(
                icao=self._this_airport["ICAO"],
                iata=self._this_airport["IATA"],
                name=self._this_airport["name"],
                city=self._this_airport["city"],
                country=self._this_airport["country"],
                region=self._this_airport["regionName"],
                lat=self._this_airport["lat"],
                lon=self._this_airport["lon"],
                alt=self._this_airport["elevation"])
            ret = self.airport.load()
            if not ret[0]:
                logger.warning("Managed airport not loaded")
                return ret
            logger.debug("..pickling airport..")
            with open(airport_cache, "wb") as fp:
                pickle.dump(self.airport, fp)
            logger.debug("..done")

        logger.debug("..setting resources..")

        self.airport.setAirspace(airspace)

        # Set for resource usage,
        # setEquipment is performed during manager's init() when loading equipment fleet.
        manager.setRamps(self.airport.getRamps())
        manager.setRunways(self.airport.getRunways())
        self.airport.setManager(manager)

        logger.debug("..updating metar..")
        self.update_metar()
        logger.debug("..done")

        self._inited = True
        return (True, "ManagedAirport::init done")

    def getInfo(self):
        return self._this_airport

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
                logger.warning(f":mkdirs: directory {d} does not exist")
        if not ok:
            return (False, "ManagedAirport::mkdirs missing mandatory base directories")

        dirs = [TEMP_DIR, CACHE_DIR, METAR_DIR, MANAGED_AIRPORT_DIR, MANAGED_AIRPORT_AODB, MANAGED_AIRPORT_CACHE]
        for d in dirs:
            if not os.path.exists(d):
                logger.warning(f":mkdirs: directory {d} does not exist")
                if create:
                    os.makedirs(d)
                    logger.info(f":mkdirs: created directory {d}")
        return (True, "ManagedAirport::init done")

    def setTimezone(self):
        """
        Build a python datetime tzinfo object for the airport local timezone.
        Since python does not have a reference to all timezone, we rely on:
        - pytz, a python implementation of  (at https://pythonhosted.org/pytz/, https://github.com/stub42/pytz)
        - timezonefinder, a python package that finds the timezone of a (lat,lon) pair (https://github.com/jannikmi/timezonefinder).
        """
        if self._this_airport is not None and "tzoffset" in self._this_airport and "tzname" in self._this_airport:
            self.timezone =  Timezone(offset=self._this_airport["tzoffset"], name=self._this_airport["tzname"])
        if self._this_airport is not None and "lat" in self._this_airport and "lon" in self._this_airport:
            tf = TimezoneFinder()
            tzname = tf.timezone_at(lng=self._this_airport["lon"], lat=self._this_airport["lat"])
            if tzname is not None:
                self.timezone =  ZoneInfo(tzname)


    def update_metar(self):
        """
        Update METAR data for managed airport.
        If self instance is loaded for a long time, this procedure should be called
        at regular interval. (It will, sometimes, be automatic (Thread).)
        (Let's dream, someday, it will load, parse and interpret TAF.)
        """
        logger.debug(":update_metar: collecting METAR..")
        # Prepare airport for each movement
        metar = Metar.new(icao=self._this_airport["ICAO"], redis=self._app.redis)
        self.airport.setMETAR(metar=metar)  # calls prepareRunways()
        logger.debug(":update_metar: ..done")


    def loadFromCache(self, dbid: int = 0):
        """
        Loads static and reference data for Managed Airport and Airport Manager from Redis datastore.

        :param      dbid:  The dbid
        :type       dbid:  int
        """
        pass