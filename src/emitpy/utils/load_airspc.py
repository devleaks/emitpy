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


logger = logging.getLogger("LoadData.Airspace")



class AirspaceData:

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

        status = self.loadNavaids()
        if not status[0]:
            return status

        prevdb = self.redis.client_info()["db"]
        self.redis.select(self.dbid)
        self.redis.select(prevdb)
        logger.debug(f":load: loaded")
        return (True, f"ManagedAirportData::load: loaded")


    # #############################@
    # AIRSPACE
    #
    def loadFixes(self):
        return (True, f"LoadData::loadAircraftPerformances: loaded fixes")

    def loadNavaids(self):
        prevdb = self.redis.client_info()["db"]
        self.redis.select(self.dbid)
        self.redis.select(prevdb)
        return (True, f"ManagedAirportData::loadNavaids: loaded navaids")

    def loadHolds(self):
        return (True, f"LoadData::loadAircraftPerformances: loaded holding positions")

    def loadAirways(self):
        return (True, f"LoadData::loadAircraftPerformances: loaded airways")

    def loadFixes(self):
        return (True, f"LoadData::loadAircraftPerformances: loaded fixes")
