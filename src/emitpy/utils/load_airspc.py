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
from emitpy.utils import Timezone, key_path, NAUTICAL_MILE
from emitpy.airspace import XPAirspace, NavAid, Terminal, Fix, AirwaySegment, ControlledPoint, CPIDENT


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

        if "*" in what or "vertex" in what:
            status = self.loadVertices()
            if not status[0]:
                return status

        if "apt" in what:
            status = self.loadAirport()
            if not status[0]:
                return status

        if "navaid" in what:
            status = self.loadNavaids()
            if not status[0]:
                return status

        if "fix" in what:
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
    def loadVertices(self):
        # Vertices = Terminals + Navaids + Fixes = Waypoints
        HEARTBEAT = 10000
        prevdb = self.redis.client_info()["db"]
        self.redis.select(self.dbid)
        cnt = 0
        errcnt = 0
        for k, v in self.airspace.vert_dict.items():
            a = ControlledPoint.parseId(ident=k)
            self.redis.json().set(key_path(REDIS_PREFIX.AIRSPACE_WAYPOINTS.value, k), Path.root_path(), v.getFeature())
            kr = key_path(REDIS_PREFIX.AIRSPACE_WAYPOINTS_INDEX.value, a[CPIDENT.IDENT])
            self.redis.sadd(kr, k)
            if cnt % HEARTBEAT == 0:
                logger.debug(f":loadVertices: {cnt}: {kr}, {k}")
            try:  # we noticed, experimentally, abs(lon) > 85 is not good...
                self.redis.geoadd(REDIS_PREFIX.AIRSPACE_WAYPOINTS_GEO_INDEX.value, (v.lon(), v.lat(), k))
            except:
                logger.debug(f":loadVertices: cannot load {k} (lat={v.lat()}, lon={v.lon()})")
                errcnt = errcnt + 1
            cnt = cnt + 1
        self.redis.select(prevdb)
        logger.debug(f":loadVertices: loaded {cnt}, {errcnt} errors")
        return (True, f"AirspaceData::loadVertices: loaded")

    def loadAirport(self):
        # Airports = Terminals
        prevdb = self.redis.client_info()["db"]
        self.redis.select(self.dbid)
        cnt = 0
        for k, v in self.airspace.vert_dict.items():
            if isinstance(v, Terminal):
                a = ControlledPoint.parseId(ident=k)
                self.redis.json().set(key_path(REDIS_PREFIX.AIRSPACE_TERMINALS.value, k), Path.root_path(), v.getInfo())
                self.redis.sadd(key_path(REDIS_PREFIX.AIRSPACE_ALL_INDEX.value, a[CPIDENT.IDENT]), k)
                self.redis.geoadd(REDIS_PREFIX.AIRSPACE_WAYPOINTS_GEO_INDEX.value, (v.lon(), v.lat(), k))
                cnt = cnt + 1
        self.redis.select(prevdb)
        logger.debug(f":loadAirport: loaded {cnt}")
        return (True, f"AirspaceData::loadAirport: loaded airports")

    def loadNavaids(self):
        prevdb = self.redis.client_info()["db"]
        self.redis.select(self.dbid)
        cnt = 0
        for k, v in self.airspace.vert_dict.items():
            if isinstance(v, NavAid):
                self.redis.json().set(key_path(REDIS_PREFIX.AIRSPACE_NAVAIDS.value, k), Path.root_path(), v.getInfo())
                a = ControlledPoint.parseId(ident=k)
                # self.redis.sadd(key_path(REDIS_PREFIX.AIRSPACE_NAVAIDS_INDEX.value, a[CPIDENT.REGION], a[CPIDENT.IDENT]), k)
                self.redis.sadd(key_path(REDIS_PREFIX.AIRSPACE_ALL_INDEX.value, a[CPIDENT.IDENT]), k)
                self.redis.geoadd(REDIS_PREFIX.AIRSPACE_WAYPOINTS_GEO_INDEX.value, (v.lon(), v.lat(), k))
                cnt = cnt + 1
                cnt = cnt + 1
        self.redis.select(prevdb)
        logger.debug(f":loadNavaids: loaded {cnt}")
        return (True, f"AirspaceData::loadNavaids: loaded navaids")

    def loadFixes(self):
        prevdb = self.redis.client_info()["db"]
        self.redis.select(self.dbid)
        cnt = 0
        errcnt = 0
        for k, v in self.airspace.vert_dict.items():
            if isinstance(v, Fix):
                self.redis.json().set(key_path(REDIS_PREFIX.AIRSPACE_FIXES.value, k), Path.root_path(), v.getInfo())
                a = ControlledPoint.parseId(ident=k)
                self.redis.sadd(key_path(REDIS_PREFIX.AIRSPACE_FIXES_INDEX.value, a[CPIDENT.REGION], a[CPIDENT.IDENT]), k)
                self.redis.sadd(key_path(REDIS_PREFIX.AIRSPACE_ALL_INDEX.value, a[CPIDENT.IDENT]), k)
                try:  # we noticed, experimentally, abs(lon) > 85 is not good...
                    self.redis.geoadd(REDIS_PREFIX.AIRSPACE_GEO_INDEX.value, (v.lon(), v.lat(), k))
                except:
                    logger.debug(f":loadFixes: cannot load {k} (lat={v.lat()}, lon={v.lon()})")
                    errcnt = errcnt + 1
                cnt = cnt + 1
        self.redis.select(prevdb)
        logger.debug(f":loadFixes: loaded {cnt}, {errcnt} errors")
        return (True, f"AirspaceData::loadNavaids: loaded fixes")

    def loadHolds(self):
        prevdb = self.redis.client_info()["db"]
        self.redis.select(self.dbid)
        cnt = 0
        for k, v in self.airspace.holds.items():
            self.redis.json().set(key_path(REDIS_PREFIX.AIRSPACE_HOLDS.value, k), Path.root_path(), v.getInfo())
            try:
                self.redis.geoadd(REDIS_PREFIX.AIRSPACE_HOLDS_GEO_INDEX.value, (v.fix.lon(), v.fix.lat(), k))
            except:
                logger.debug(f":loadHolds: cannot load {k} (lat={v.fix.lat()}, lon={v.fix.lon()})")
            cnt = cnt + 1
        # We preselect holds in the vicinity of the managed airport
        logger.debug(f":loadHolds: preselecting {MANAGED_AIRPORT['ICAO']} local holds..")
        store = key_path(REDIS_PREFIX.AIRSPACE_HOLDS.value, MANAGED_AIRPORT["ICAO"])
        self.redis.geosearchstore(name=REDIS_PREFIX.AIRSPACE_HOLDS_GEO_INDEX.value,
                                  longitude=MANAGED_AIRPORT["lon"],
                                  latitude=MANAGED_AIRPORT["lat"],
                                  unit='km',
                                  radius=100*NAUTICAL_MILE,
                                  dest=store)
        logger.debug(f":loadHolds: .. stored in {store} ..done")
        #
        self.redis.select(prevdb)
        logger.debug(f":loadHolds: loaded {cnt}")
        return (True, f"AirspaceData::loadHolds: loaded holding positions")

    def loadAirways(self):
        # ~ loadEdges.
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
