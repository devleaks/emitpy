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


logger = logging.getLogger("LoadData.Network")



class NetworkData:

    @staticmethod
    def data_is_loaded(redis):
        """
        Simplistic but ok for now

        :param      redis:  The redis
        :type       redis:  { type_description }
        """
        t = redis.get("aircraft-performances:A320")
        return t is not None


    def __init__(self, redis):
        self.redis = redis

        status = self.loadAircraftTypes()
        if not status[0]:
            return status


    # #############################@
    # MANAGED AIRPORT
    #
    def loadTaxiways(self):
        return (True, f"LoadData::loadAircraftPerformances: loaded {len(aircrafttypes)} aircraft types")

    def loadServiceRoads(self):
        return (True, f"LoadData::loadAircraftPerformances: loaded {len(aircrafttypes)} aircraft types")

