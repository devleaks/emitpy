"""
Loads refereence data into Redis cache.
"""
import os
import yaml
import json
import logging
from redis.commands.json.path import Path

from emitpy.airspace import XPAirspace, Metar
from emitpy.business import Airline, Company
from emitpy.aircraft import AircraftType, AircraftPerformance, Aircraft
from emitpy.airport import Airport, AirportBase, XPAirport
from emitpy.business import AirportManager
from emitpy.constants import REDIS_DB, REDIS_PREFIX
from emitpy.utils import Timezone, key_path

logger = logging.getLogger("LoadData.Generic")


class GenericData:

    @staticmethod
    def data_is_loaded(redis, dbid = REDIS_DB.REF.value):
        """
        Simplistic but ok for now

        :param      redis:  The redis
        :type       redis:  { type_description }
        """
        prevdb = self.redis.client_info()["db"]
        self.redis.select(self.dbid)
        t = redis.get("aircrafs:performances:A320")
        self.redis.select(prevdb)
        return t is not None


    def __init__(self, redis, dbid = REDIS_DB.REF.value):
        self.redis = redis
        self.dbid = dbid


    def load(self):
        status = self.loadAircraftTypes()
        if not status[0]:
            return status

        status = self.loadAircraftPerformances()
        if not status[0]:
            return status

        # status = self.loadAirports()
        # if not status[0]:
        #     return status

        status = self.loadAirlines()
        if not status[0]:
            return status

        logger.debug(f":load: loaded")
        return (True, f"ManagedAirportFlightData::load: loaded")


    def loadAircraftTypes(self):
        AircraftType.loadAll()
        prevdb = self.redis.client_info()["db"]
        self.redis.select(self.dbid)
        for a in AircraftType._DB.values():
            a.save(REDIS_PREFIX.AIRCRAFT_TYPES.value, self.redis)
        self.redis.select(prevdb)
        logger.debug(f":loadAircraftTypes: loaded {len(AircraftType._DB)} aircraft types")
        return (True, f"GenericData::loadAircraftTypes: loaded aircraft types")


    def loadAircraftPerformances(self):
        prevdb = self.redis.client_info()["db"]
        self.redis.select(self.dbid)

        AircraftPerformance.loadAll()
        for a in AircraftPerformance._DB_PERF.values():
            a.save(REDIS_PREFIX.AIRCRAFT_PERFS.value, self.redis)
        # Aircraft equivalences
        logger.debug(f":loadAircraftPerformances: loaded {len(AircraftPerformance._DB_PERF)} aircraft performances")

        AircraftType.loadAircraftEquivalences()
        self.redis.json().set(REDIS_PREFIX.AIRCRAFT_EQUIS.value, Path.root_path(), AircraftPerformance._DB_EQUIVALENCE)
        for k, v in AircraftPerformance._DB_EQUIVALENCE.items():
            self.redis.json().set(key_path(REDIS_PREFIX.AIRCRAFT_EQUIS.value, k), Path.root_path(), v)
        logger.debug(f":loadAircraftPerformances: loaded {len(AircraftPerformance._DB_EQUIVALENCE)} aircraft equivalences")

        self.redis.select(prevdb)
        return (True, f"GenericData::loadAircraftPerformances: loaded aircraft performances and equivalences")


    def loadAirports(self):
        prevdb = self.redis.client_info()["db"]
        self.redis.select(self.dbid)

        Airport.loadAll()
        for a in Airport._DB.values():
            a.save(REDIS_PREFIX.AIRPORTS.value, self.redis)

        logger.debug(f":loadAircraftPerformances: loaded {len(Airport._DB)} airports")
        self.redis.select(prevdb)
        return (True, f"GenericData::loadAirports: loaded airports")


    def loadAirlines(self):
        prevdb = self.redis.client_info()["db"]
        self.redis.select(self.dbid)

        Airline.loadAll()
        for a in Airline._DB.values():
            a.save(key_path(REDIS_PREFIX.AIRLINES.value, REDIS_PREFIX.ICAO.value), self.redis, mode=REDIS_PREFIX.ICAO.value)
        for a in Airline._DB_IATA.values():
            a.save(key_path(REDIS_PREFIX.AIRLINES.value, REDIS_PREFIX.IATA.value), self.redis, mode=REDIS_PREFIX.IATA.value)

        logger.debug(f":loadAircraftPerformances: loaded {len(Airline._DB)} airlines")
        self.redis.select(prevdb)
        return (True, f"GenericData::loadAirlines: loaded airlines")


    def loadAirlineRoutes(self):
        return (False, f"GenericData::loadAirlineRoutes: no free global feed for airline routes")
