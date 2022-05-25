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


    def load(self, what = ["*"]):

        if "*" in what or "actype" in what:
            status = self.loadAircraftTypes()
            if not status[0]:
                return status

        if "*" in what or "acperf" in what:
            status = self.loadAircraftPerformances()
            if not status[0]:
                return status

        if "*" in what or "acequiv" in what:
            status = self.loadAircraftEquivalences()
            if not status[0]:
                return status

        if "*" in what or "airport" in what:
            status = self.loadAirports()
            if not status[0]:
                return status

        if "*" in what or "airline" in what:
            status = self.loadAirlines()
            if not status[0]:
                return status

        if "*" in what or "airroute" in what:
            status = self.loadAirlineRoutes()
            if not status[0]:
                return status

        logger.debug(f":load: loaded")
        return (True, f"GenericData::load: loaded")


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

        AircraftType.loadAll()
        AircraftPerformance.loadAll()
        for a in AircraftPerformance._DB_PERF.values():
            a.save(REDIS_PREFIX.AIRCRAFT_PERFS.value, self.redis)

        def saveid(k):
            AircraftPerformance._DB_PERF[k].save_id = k
            return AircraftPerformance._DB_PERF[k]

        g1 = map(saveid, AircraftPerformance._DB_PERF.keys())
        g2 = filter(lambda a: a.check_availability(), g1)
        gdict = dict([(v.save_id, v.getInfo()) for v in g2])
        self.redis.json().set(REDIS_PREFIX.AIRCRAFT_PERFS.value, Path.root_path(), gdict)
        a = list(gdict.values())
        self.redis.json().set(REDIS_PREFIX.AIRCRAFT_PERFS.value + "2", Path.root_path(), a)
        self.redis.select(prevdb)

        logger.debug(f":loadAircraftPerformances: loaded {len(gdict)}/{len(AircraftPerformance._DB_PERF)} aircraft performances")
        return (True, f"GenericData::loadAircraftPerformances: loaded aircraft performances")


    def loadAircraftEquivalences(self):
        prevdb = self.redis.client_info()["db"]
        self.redis.select(self.dbid)

        AircraftType.loadAircraftEquivalences()
        self.redis.json().set(REDIS_PREFIX.AIRCRAFT_EQUIS.value, Path.root_path(), AircraftPerformance._DB_EQUIVALENCE)
        for k, v in AircraftPerformance._DB_EQUIVALENCE.items():
            self.redis.json().set(key_path(REDIS_PREFIX.AIRCRAFT_EQUIS.value, k), Path.root_path(), v)
        self.redis.json().set(REDIS_PREFIX.AIRCRAFT_EQUIS.value, Path.root_path(), AircraftPerformance._DB_EQUIVALENCE)
        self.redis.select(prevdb)

        logger.debug(f":loadAircraftEquivalences: loaded {len(AircraftPerformance._DB_EQUIVALENCE)} aircraft equivalences")
        return (True, f"GenericData::loadAircraftEquivalences: loaded aircraft equivalences")


    def loadAirports(self):
        prevdb = self.redis.client_info()["db"]
        self.redis.select(self.dbid)

        Airport.loadAll()
        for a in Airport._DB.values():
            a.save(REDIS_PREFIX.AIRPORTS.value, self.redis)
        self.redis.json().set(key_path(REDIS_PREFIX.AIRPORTS.value, REDIS_PREFIX.ICAO.value), Path.root_path(), Airport._DB)
        self.redis.json().set(key_path(REDIS_PREFIX.AIRPORTS.value, REDIS_PREFIX.IATA.value), Path.root_path(), Airport._DB_IATA)
        logger.debug(f":loadAirports: loaded {len(Airport._DB)} airports")
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

        a = dict([(k, v.getInfo()) for k, v in Airline._DB.items()])
        self.redis.json().set(key_path(REDIS_PREFIX.AIRLINES.value, REDIS_PREFIX.ICAO.value), Path.root_path(), a)
        a = dict([(k, v.getInfo()) for k, v in Airline._DB_IATA.items()])
        self.redis.json().set(key_path(REDIS_PREFIX.AIRLINES.value, REDIS_PREFIX.IATA.value), Path.root_path(), a)

        # temp
        a = [a.getInfo() for a in Airline._DB.values()]
        self.redis.json().set(key_path(REDIS_PREFIX.AIRLINES.value), Path.root_path(), a)

        logger.debug(f":loadAirlines: loaded {len(Airline._DB)} airlines")
        self.redis.select(prevdb)
        return (True, f"GenericData::loadAirlines: loaded airlines")


    def loadAirlineRoutes(self):
        return (False, f"GenericData::loadAirlineRoutes: no free global feed for airline routes")

