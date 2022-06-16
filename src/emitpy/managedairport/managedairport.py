import logging

import json
from redis.commands.json.path import Path
from fastapi.encoders import jsonable_encoder

from emitpy.airspace import XPAirspace, Metar
from emitpy.business import Airline, Company
from emitpy.aircraft import AircraftType, AircraftPerformance, Aircraft
from emitpy.airport import Airport, AirportBase, XPAirport
from emitpy.business import AirportManager
from emitpy.constants import REDIS_DATABASE, ID_SEP
from emitpy.utils import Timezone, key_path

logger = logging.getLogger("ManagedAirport")


class ManagedAirport:
    """
    Wrapper class to load all managed airport parts.
    """

    def __init__(self, airport, app):
        self._this_airport = airport
        self._inited = False
        self._app = app  # context
        self.airport = None
        self.timezone = Timezone(offset=self._this_airport["tzoffset"], name=self._this_airport["tzname"])


    def init(self, load_airways: bool = False):
        """
        Load entire managed airport data together with airport manager.
        """
        if self._inited:
            return (False, "ManagedAirport::init already inited")

        airspace = XPAirspace(load_airways=load_airways)
        logger.debug("loading airspace..")
        ret = airspace.load(self._app.redis)
        if not ret[0]:
            logger.warning("Airspace not loaded")
            return ret
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
        operator = Company(orgId="Airport Operator",
                           classId="Airport Operator",
                           typeId="Airport Operator",
                           name=self._this_airport["operator"])
        manager = AirportManager(icao=self._this_airport["ICAO"], operator=operator, app=self._app)
        ret = manager.load(self._app.redis)
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

        self._inited = True
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


    def loadFromCache(self, dbid: int = 0):
        """
        Loads static and reference data for Managed Airport and Airport Manager from Redis datastore.

        :param      dbid:  The dbid
        :type       dbid:  int
        """
        pass