import sys
sys.path.append('/Users/pierre/Developer/oscars/emitpy/src')
import logging

import os
import yaml
import json

import logging
from redis.commands.json.path import Path

from emitpy.parameters import MANAGED_AIRPORT
from emitpy.constants import REDIS_DB, REDIS_PREFIX, ID_SEP
from emitpy.utils import Timezone, key_path
from emitpy.airspace import XPAirspace, NavAid, Terminal, Fix, AirwaySegment


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

        self.airspace = XPAirspace()
        logger.debug("loading airspace..")
        self.airspace.load()
        logger.debug("..done")


    def load(self, what = ["*"]):

        if "*" in what or "apt" in what:
            status = self.loadAirport()
            if not status[0]:
                return status

        if "*" in what or "navaid" in what:
            status = self.loadNavaids()
            if not status[0]:
                return status

        if "*" in what or "fix" in what:
            status = self.loadFixes()
            if not status[0]:
                return status

        if "*" in what or "hold" in what:
            status = self.loadHolds()
            if not status[0]:
                return status

        if "*" in what or "airway" in what:
            status = self.loadAirways()
            if not status[0]:
                return status

        prevdb = self.redis.client_info()["db"]
        self.redis.select(self.dbid)
        self.redis.select(prevdb)
        logger.debug(f":load: loaded")
        return (True, f"AirspaceData::load: loaded")


    # #############################@
    # AIRSPACE
    #
    def loadAirport(self):
        prevdb = self.redis.client_info()["db"]
        self.redis.select(self.dbid)
        cnt = 0
        for k, v in self.airspace.vert_dict.items():
            varr = k.split(ID_SEP)
            if isinstance(v, Terminal):
                self.redis.json().set(key_path(REDIS_PREFIX.AIRSPACE_TERMINALS.value, k), Path.root_path(), v.getInfo())
                cnt = cnt + 1
        self.redis.select(prevdb)
        logger.debug(f":loadAirport: loaded {cnt}")
        return (True, f"AirspaceData::loadAirport: loaded airports")

    def loadNavaids(self):
        prevdb = self.redis.client_info()["db"]
        self.redis.select(self.dbid)
        cnt = 0
        for k, v in self.airspace.vert_dict.items():
            varr = k.split(ID_SEP)
            if isinstance(v, NavAid):
                self.redis.json().set(key_path(REDIS_PREFIX.AIRSPACE_NAVAIDS.value, k), Path.root_path(), v.getInfo())
                cnt = cnt + 1
        self.redis.select(prevdb)
        logger.debug(f":loadNavaids: loaded {cnt}")
        return (True, f"AirspaceData::loadNavaids: loaded navaids")

    def loadFixes(self):
        prevdb = self.redis.client_info()["db"]
        self.redis.select(self.dbid)
        cnt = 0
        for k, v in self.airspace.vert_dict.items():
            varr = k.split(ID_SEP)
            if isinstance(v, Fix):
                self.redis.json().set(key_path(REDIS_PREFIX.AIRSPACE_FIXES.value, k), Path.root_path(), v.getInfo())
                cnt = cnt + 1
        self.redis.select(prevdb)
        logger.debug(f":loadFixes: loaded {cnt}")
        return (True, f"AirspaceData::loadNavaids: loaded fixes")

    def loadHolds(self):
        prevdb = self.redis.client_info()["db"]
        self.redis.select(self.dbid)
        cnt = 0
        for k, v in self.airspace.holds.items():
            self.redis.json().set(key_path(REDIS_PREFIX.AIRSPACE_HOLDS.value, k), Path.root_path(), v.getInfo())
            cnt = cnt + 1
        self.redis.select(prevdb)
        logger.debug(f":loadHolds: loaded {cnt}")
        return (True, f"AirspaceData::loadHolds: loaded holding positions")

    def loadAirways(self):
        prevdb = self.redis.client_info()["db"]
        self.redis.select(self.dbid)
        cnt = 0
        for v in self.airspace.edges_arr:
            if isinstance(v, AirwaySegment):
                self.redis.json().set(key_path(REDIS_PREFIX.AIRSPACE_AIRWAYS.value, v.getKey()), Path.root_path(), v.getInfo())
                cnt = cnt + 1
        self.redis.select(prevdb)
        logger.debug(f":loadAirways: loaded {cnt}")
        return (True, f"AirspaceData::loadAirways: loaded airways")
