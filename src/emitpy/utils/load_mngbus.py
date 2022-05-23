"""
Loads refereence data into Redis cache.
"""
import os
import yaml
import json

import logging
from redis.commands.json.path import Path

from emitpy.parameters import MANAGED_AIRPORT
from emitpy.constants import REDIS_DB, REDIS_PREFIX
from emitpy.utils import Timezone, key_path
from emitpy.business import Company, AirportManager


logger = logging.getLogger("LoadData.AirportManager")



class ManagedAirportData:

    @staticmethod
    def data_is_loaded(redis, dbid = REDIS_DB.REF.value):
        """
        Simplistic but ok for now

        :param      redis:  The redis
        :type       redis:  { type_description }
        """
        prevdb = self.redis.client_info()["db"]
        self.redis.select(self.dbid)
        t = redis.get("airport")
        self.redis.select(prevdb)
        return t is not None


    def __init__(self, redis, dbid = REDIS_DB.REF.value):
        self.redis = redis
        self.dbid = dbid
        operator = Company(orgId="Airport Operator",
                           classId="Airport Operator",
                           typeId="Airport Operator",
                           name=MANAGED_AIRPORT["operator"])
        self.manager = AirportManager(icao=MANAGED_AIRPORT["ICAO"],
                                      operator=operator,
                                      app=self)
        logger.debug("loading..")
        self.manager.load()
        logger.debug("..done")


    def load(self):

        status = self.loadAirlineFrequencies()
        if not status[0]:
            return status

        status = self.loadAirlineRoutes()
        if not status[0]:
            return status

        status = self.loadAirlineRouteFrequencies()
        if not status[0]:
            return status

        status = self.loadCompanies()
        if not status[0]:
            return status

        status = self.loadGSE()
        if not status[0]:
            return status

        prevdb = self.redis.client_info()["db"]
        self.redis.select(self.dbid)
        self.redis.json().set(REDIS_PREFIX.AIRPORT.value, Path.root_path(), MANAGED_AIRPORT)
        self.redis.select(prevdb)

        logger.debug(f":load: loaded")
        return (True, f"ManagedAirportData::load: loaded")


    def loadAirlineFrequencies(self):
        prevdb = self.redis.client_info()["db"]
        self.redis.select(self.dbid)
        for k, v in self.manager.airline_frequencies.items():
            self.redis.json().set(key_path(REDIS_PREFIX.AIRLINES.value, k), Path.root_path(), v)
        self.redis.select(prevdb)
        return (True, f"ManagedAirportData::loadAirlineFrequencies: loaded airline frequencies")


    def loadAirlineRoutes(self):
        prevdb = self.redis.client_info()["db"]
        self.redis.select(self.dbid)
        for k, v in self.manager.airline_route_frequencies.items():
            for k1, v1 in v.items():
                self.redis.json().set(key_path(REDIS_PREFIX.AIRROUTES.value, "airlines", k), Path.root_path(), list(v.keys()))
                k2 = key_path(REDIS_PREFIX.AIRROUTES.value, "airports", k1)
                if self.redis.json().get(k2) is None:
                    self.redis.json().set(k2, Path.root_path(), [k])
                else:
                    self.redis.json().arrappend(k2, Path.root_path(), k)
        self.redis.select(prevdb)
        return (True, f"ManagedAirportData::loadAirlineRoutes: loaded airline routes")


    def loadAirlineRouteFrequencies(self):
        prevdb = self.redis.client_info()["db"]
        self.redis.select(self.dbid)
        for k, v in self.manager.airline_route_frequencies.items():
            for k1, v1 in v.items():
                self.redis.json().set(key_path(REDIS_PREFIX.AIRROUTES.value, "airlines", k, k1), Path.root_path(), v1)
                self.redis.json().set(key_path(REDIS_PREFIX.AIRROUTES.value, "airports", k1, k), Path.root_path(), v1)
        self.redis.select(prevdb)
        return (True, f"ManagedAirportData::loadAirlineRouteFrequencies: loaded airline route frequencies")


    def loadCompanies(self):
        prevdb = self.redis.client_info()["db"]
        self.redis.select(self.dbid)
        for k, v in self.manager.companies.items():
            self.redis.json().set(key_path(REDIS_PREFIX.COMPANIES.value, k), Path.root_path(), v.getInfo())
        for k, v in self.manager.people.items():
            self.redis.json().set(key_path("business", "people", k), Path.root_path(), v)
        self.redis.select(prevdb)
        return (True, f"ManagedAirportData::loadCompanies: loaded companies")


    def loadGSE(self):
        prevdb = self.redis.client_info()["db"]
        self.redis.select(self.dbid)
        for k, v in self.manager.vehicle_by_type.items():
            for v1 in v:
                self.redis.json().set(key_path(REDIS_PREFIX.GSE.value, k, v1.getKey()), Path.root_path(), v1.getInfo())
        self.redis.select(prevdb)
        return (True, f"ManagedAirportData::loadGSE: loaded GSE")


