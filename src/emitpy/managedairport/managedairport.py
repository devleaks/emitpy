import logging

from emitpy.airspace import XPAirspace, Metar
from emitpy.business import Airline, Company
from emitpy.aircraft import AircraftType, AircraftPerformance, Aircraft
from emitpy.airport import Airport, AirportBase, XPAirport
from emitpy.business import AirportManager


logger = logging.getLogger("ManagedAirport")


class ManagedAirport:
    """
    Wrapper class to load all managed airport parts.
    """

    def __init__(self, airport, app, cache: bool=False):
        self._this_airport = airport
        self._app = app  # context
        self._cache = cache
        self.airport = None

    def init(self):
        """
        Load entire managed airport data together with airport manager.
        """
        airspace = XPAirspace()
        logger.debug("loading airspace..")
        airspace.load()
        logger.debug("..done")

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
        operator = Company(orgId="Airport Operator",
                           classId="Airport Operator",
                           typeId="Airport Operator",
                           name=self._this_airport["operator"])
        manager = AirportManager(icao=self._this_airport["ICAO"], operator=operator, app=self._app)
        ret = manager.load()
        if not ret[0]:
            logger.warning("Airport manager not loaded")
            return ret

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

        logger.debug("..setting resources..")

        self.airport.setAirspace(airspace)

        # Set for resource usage
        manager.setRamps(self.airport.getRamps())
        manager.setRunways(self.airport.getRunways())
        self.airport.setManager(manager)


        logger.debug("..updating metar..")
        self.update_metar()
        logger.debug("..done")

        if self._cache:
            logger.debug("..caching..")
            self.cache()
            logger.debug("..done")

        return (True, "ManagedAirport::init done")


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


    def cache(self, dbid: int = 1):
        """
        Saves Managed Airport and Airport Manager static data into Redis datastore.

        :param      dbid:  The dbid
        :type       dbid:  int
        """
        redis = self._app.redis
        # Airports
        logger.debug(":cache: caching..")
        prevdb = redis.client_info()["db"]
        redis.select(dbid)
        # logger.debug(":cache: ..airports..")
        # for a in Airport._DB.values():
        #     a.save("airports", self._app.redis)
        # Airports + procedures
        # Aircraft Types
        logger.debug(":cache: ..aircrafts..")
        for a in AircraftType._DB.values():
            a.save("aircraft-types", self._app.redis)
        # Aircraft types + performances
        for a in AircraftPerformance._DB_PERF.values():
            a.save("aircraft-performances", self._app.redis)
        # Airlines
        # Airlines + routes
        # Airspace (terminals, navaids, fixes, airways)
        #
        redis.select(prevdb)
        logger.debug(":cache: ..done")


    def cache_static_lovs(self, dbid: int = 0):
        logger.debug(":cache_static_lovs: caching..")
        prevdb = redis.client_info()["db"]
        redis.select(dbid)

        redis.select(prevdb)
        logger.debug(":cache_static_lovs: ..done")


    def loadFromCache(self, dbid: int = 0):
        """
        Loads static and reference data for Managed Airport and Airport Manager from Redis datastore.

        :param      dbid:  The dbid
        :type       dbid:  int
        """
        pass