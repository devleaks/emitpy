"""
Loads refereence data into Redis cache.
"""
import os
import yaml
import json

import logging
from redis.commands.json.path import Path

from emitpy.business import Airline
from emitpy.airport.xpairport import XPAirport

from emitpy.parameters import MANAGED_AIRPORT, DATA_DIR
from emitpy.constants import REDIS_DB, REDIS_PREFIX
from emitpy.utils import Timezone, key_path

logger = logging.getLogger("LoadData.ManagedAirport")



class ManagedAirportFlightData:

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

        self.airport = XPAirport(
            icao=MANAGED_AIRPORT["ICAO"],
            iata=MANAGED_AIRPORT["IATA"],
            name=MANAGED_AIRPORT["name"],
            city=MANAGED_AIRPORT["city"],
            country=MANAGED_AIRPORT["country"],
            region=MANAGED_AIRPORT["regionName"],
            lat=MANAGED_AIRPORT["lat"],
            lon=MANAGED_AIRPORT["lon"],
            alt=MANAGED_AIRPORT["elevation"])
        logger.debug("loading airport..")
        self.airport.load()
        logger.debug("..done")


    def load(self):
        status = self.loadFlightPlans()
        if not status[0]:
            return status

        status = self.loadRamps()
        if not status[0]:
            return status

        status = self.loadRunways()
        if not status[0]:
            return status

        status = self.loadAirwayPOIS()
        if not status[0]:
            return status

        status = self.loadServicePOIS()
        if not status[0]:
            return status

        status = self.loadServiceDestinations()
        if not status[0]:
            return status

        status = self.loadCheckpoints()
        if not status[0]:
            return status

        logger.debug(f":load: loaded")
        return (True, f"ManagedAirportFlightData::load: loaded")


    def loadFlightPlans(self):
        prevdb = self.redis.client_info()["db"]
        self.redis.select(self.dbid)

        flightplan_cache = os.path.join(DATA_DIR, "managedairport", MANAGED_AIRPORT["ICAO"], "flightplans")
        for f in sorted(os.listdir(flightplan_cache)):
            if f.endswith(".json"):
                fn = os.path.join(flightplan_cache, f)
                kn = f.replace(".json", "").replace("-", ":").lower()
                with open(fn) as data_file:
                    data = json.load(data_file)
                    logger.debug(f":loadFlightPlans: loading {fn}")
                    self.redis.json().set(key_path(REDIS_PREFIX.FLIGHTPLAN_FPDB.value, kn), Path.root_path(), data)
            if f.endswith(".geojson"):
                fn = os.path.join(flightplan_cache, f)
                kn = f.replace(".geojson", "").replace("-", ":").lower()
                with open(fn) as data_file:
                    data = json.load(data_file)
                    logger.debug(f":loadFlightPlans: loading {fn}")
                    self.redis.json().set(key_path(REDIS_PREFIX.FLIGHTPLAN_GEOJ.value, kn), Path.root_path(), data)

        airportplan_cache = os.path.join(DATA_DIR, "airports", "fpdb")
        for f in sorted(os.listdir(airportplan_cache)):
            if f.endswith(".json"):
                fn = os.path.join(airportplan_cache, f)
                kn = f.replace(".json", "").replace("-", ":").lower()
                with open(fn) as data_file:
                    data = json.load(data_file)
                    logger.debug(f":loadFlightPlans: loading {fn}")
                    self.redis.json().set(key_path(REDIS_PREFIX.FLIGHTPLAN_APTS.value, kn), Path.root_path(), data)

        self.redis.select(prevdb)
        return (True, f"LoadData::loadFlightPlans: loaded flight plans")


    def loadRamps(self):
        prevdb = self.redis.client_info()["db"]
        self.redis.select(self.dbid)
        for k, v in self.airport.ramps.items():
            self.redis.json().set(key_path(REDIS_PREFIX.AIRPORT.value, REDIS_PREFIX.GEOJSON.value, REDIS_PREFIX.RAMPS.value, k), Path.root_path(), v)
        self.redis.select(prevdb)

        logger.debug(f":loadRamps: loaded {len(self.airport.ramps)}")
        return (True, f"LoadData::loadRamps: loaded ramps")


    def loadRunways(self):
        prevdb = self.redis.client_info()["db"]
        self.redis.select(self.dbid)
        for k, v in self.airport.runways.items():
            if hasattr(v, "end"):
                v.setProp("opposite-end", v.end.getProp("name"))
                logger.warning(f":loadRunways: removed circular dependency {v.getProp('name')} <> {v.end.getProp('name')}")
                del v.end
            self.redis.json().set(key_path(REDIS_PREFIX.AIRPORT.value, REDIS_PREFIX.GEOJSON.value, REDIS_PREFIX.RUNWAYS.value, k), Path.root_path(), v)
        self.redis.select(prevdb)

        logger.debug(f":loadRamps: loaded {len(self.airport.runways)}")
        return (True, f"LoadData::loadRamps: loaded runways")


    def loadAirwayPOIS(self):
        prevdb = self.redis.client_info()["db"]
        self.redis.select(self.dbid)
        for k, v in self.airport.aeroway_pois.items():
            self.redis.json().set(key_path(REDIS_PREFIX.AIRPORT.value, REDIS_PREFIX.GEOJSON.value, REDIS_PREFIX.AEROWAYS.value, k), Path.root_path(), v)
        self.redis.select(prevdb)

        logger.debug(f":loadAirwayPOIS: loaded {len(self.airport.aeroway_pois)}")
        return (True, f"LoadData::loadAirwayPOIS: loaded airway points of interest")


    def loadServicePOIS(self):
        prevdb = self.redis.client_info()["db"]
        self.redis.select(self.dbid)
        for k, v in self.airport.service_pois.items():
            self.redis.json().set(key_path(REDIS_PREFIX.AIRPORT.value, REDIS_PREFIX.GEOJSON.value, REDIS_PREFIX.GROUNDSUPPORT.value, k), Path.root_path(), v)
        self.redis.select(prevdb)

        logger.debug(f":loadServicePOIS: loaded {len(self.airport.service_pois)}")
        return (True, f"LoadData::loadServicePOIS: loaded service points of interest")


    def loadServiceDestinations(self):
        prevdb = self.redis.client_info()["db"]
        self.redis.select(self.dbid)
        for k, v in self.airport.service_destinations.items():
            self.redis.json().set(key_path(REDIS_PREFIX.AIRPORT.value, REDIS_PREFIX.GEOJSON.value, REDIS_PREFIX.GROUNDSUPPORT_DESTINATION.value, k), Path.root_path(), v)
        self.redis.select(prevdb)

        logger.debug(f":loadServiceDestinations: loaded {len(self.airport.service_destinations)}")
        return (True, f"LoadData::loadServiceDestinations: loaded service points of interest")


    def loadCheckpoints(self):
        prevdb = self.redis.client_info()["db"]
        self.redis.select(self.dbid)
        for k, v in self.airport.check_pois.items():
            self.redis.json().set(key_path(REDIS_PREFIX.AIRPORT.value, REDIS_PREFIX.GEOJSON.value, REDIS_PREFIX.MISSION.value, k), Path.root_path(), v)
        self.redis.select(prevdb)

        logger.debug(f":loadCheckpoints: loaded {len(self.airport.check_pois)}")
        return (True, f"LoadData::loadCheckpoints: loaded check points")

