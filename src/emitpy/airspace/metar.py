"""
A METAR is a weather situation at a named location, usually an airport.
"""
import os
import re
import logging
import importlib
import csv
from io import StringIO
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone

import requests_cache
import requests

from metar import Metar as MetarLib

from emitpy.constants import REDIS_DATABASE, REDIS_DB
from emitpy.parameters import METAR_DIR
from emitpy.utils import key_path
from .atmap import ATMAP

logger = logging.getLogger("Metar")


def round_dt(dt, delta):  # rounds date to delta after date.
    return dt + (datetime.min - dt.replace(tzinfo=None)) % delta

def normalize_dt(dt):
    dtutc = dt.astimezone(tz=timezone.utc)
    dtret = round_dt(dtutc - timedelta(minutes=30), timedelta(minutes=30))
    logger.debug(f"{dt}: {dtutc}=>{dtret}")
    return dtret


class Metar(ABC):
    """
    Loads cached METAR for ICAO or fetch **current** from source.
    """
    def __init__(self, icao: str, redis = None):
        self.icao = icao
        self.moment = datetime.now().astimezone()
        self.moment_norm = normalize_dt(self.moment)
        self.metar = None   # parsed metar
        self.raw = None     # metar string
        self.atmap = None   # Eurocontrol ATMAP coefficient
        self.redis = redis

        if redis is None and not os.path.exists(METAR_DIR) or not os.path.isdir(METAR_DIR):
            logger.warning(f"no Metar directory {METAR_DIR}")


    # ####################################
    # METAR Emitpy Interface
    #
    @staticmethod
    def new(icao: str, redis=None, method: str = "MetarFPDB"):
        """
        Create a new Metar using the supplied fetch method.

        :param      icao:    The icao
        :type       icao:    str
        :param      redis:   The redis
        :type       redis:   { type_description }
        :param      method:  The method
        :type       method:  str
        """
        metarclasses = importlib.import_module(name=".airspace.metar", package="emitpy")
        if hasattr(metarclasses, method):
            doit = getattr(metarclasses, method)
            return doit(icao, redis)
        else:
            logger.warning(f"could not get Metar implementation {method}")
        return None

    def getWindDirection(self):
        """
        Returns wind direction if any, or None if no wind or multiple directions.
        Used at Airport to determine runways in use.
        """
        return self.metar.wind_dir if self.metar is not None else None

    def getPrecipitation(self):
        """
        Returns amount of precipitations in CM of water. No difference between water, ice, snow, hail...
        Used in flights to calculate landing distance of an aircraft.
        """
        if self.metar is not None:
            if self.metar.precip_1hr is not None:
                if self.metar.precip_1hr.istrace():
                    return 0.1
                return self.metar.precip_1hr.value(units="CM")
        return 0


    # ####################################
    # METAR internals...
    #
    def init(self):
        self.load()
        if self.raw is None:
            self.fetch()
            self.save()

    def setDatetime(self, moment: datetime = datetime.now().astimezone()):
        self.moment = moment
        self.moment_norm = normalize_dt(self.moment)
        self.metar = None
        self.raw = None
        self.init()

    def get(self):
        return self.raw

    def getRaw(self):
        return self.raw

    def hasMetar(self):
        return self.metar is not None

    def getInfo(self):
        return {
            "icao": self.icao,
            "date": self.moment_norm.isoformat(),
            "metar": self.raw
        }

    @abstractmethod
    def fetch(self):
        """
        Fetches the METAR from its source.
        """
        return (False, "Metar::fetch: abstract class")

    def save(self):
        if self.redis is not None:
            return self.saveToCache()
        else:
            return self.saveFile()

    def load(self):
        if self.redis is not None:
            return self.loadFromCache()
        else:
            return self.loadFile()

    def saveFileName(self):
        nowstr = self.cacheKeyName()
        return os.path.join(METAR_DIR, self.icao + "-" + nowstr + ".metar")

    def saveFile(self):
        if self.raw is not None:
            fn = self.saveFileName()
            if not os.path.exists(fn):
                logger.warning(f"saving into {fn} '{self.raw}'")
                with open(fn, "w") as outfile:
                    outfile.write(self.raw)
            else:
                logger.warning(f"already exist {fn}")
            return (True, "Metar::saveFile: saved")
        return (False, "Metar::saveFile: no METAR to saved")

    def loadFile(self):
        fn = self.saveFileName()
        if os.path.exists(fn):
            logger.debug(f"found {fn}")
            try:
                with open(fn, "r") as fp:
                    self.raw = fp.readline()
            except:
                logger.debug(f"problem reading from {fn}", exc_info=True)
                self.raw = None

            if self.raw is not None:
                return self.parse()
                return (True, "Metar::loadFile: loaded and parsed")
            return (False, "Metar::loadFile: not loaded")
        else:
            logger.debug(f"file not found {fn}")
        return (False, "Metar::loadFile: not loaded")

    def cacheKeyName(self):
        """
        Gets the full data time for storage. METAR only have latest DDHHMM, with no year or month.
        So we add them to Redis keys and filenames.
        """
        return self.moment_norm.strftime('%Y%m-%d%H%MZ')

    def saveToCache(self):
        if self.raw is not None:
            prevdb = self.redis.client_info()["db"]
            self.redis.select(REDIS_DB.PERM.value)
            nowstr = self.cacheKeyName()
            metid = key_path(REDIS_DATABASE.METAR.value, self.raw[0:4], nowstr)
            if not self.redis.exists(metid):
                self.redis.set(metid, self.raw)
                self.redis.select(prevdb)
                logger.debug(f"saved {metid}")
                return (True, "Metar::saveToCache: saved")
            else:
                self.redis.select(prevdb)
                logger.warning(f"already exist {metid}")
        else:
            logger.warning(f"no metar to save")
        return (False, "Metar::saveToCache: not saved")

    def loadFromCache(self):
        if self.redis is not None:
            nowstr = self.cacheKeyName()
            metid = REDIS_DATABASE.METAR.value + ":" + self.icao + ":" + nowstr
            if self.redis.exists(metid):
                logger.debug(f"found {metid}")
                raw = self.redis.get(metid)
                self.raw = raw.decode("UTF-8")
                if self.raw is not None:
                    return self.parse()
                    return (True, "Metar::loadFromCache: loaded and parsed")
                return (False, "Metar::loadFromCache: failed to get")
            else:
                logger.debug(f"not found {metid}")
        return (False, "Metar::loadFromCache: failed to load")

    def parse(self):
        """
        Clear protected parsing of Metar.
        If parsing succeeded, result is kept
        """
        try:
            parsed = MetarLib.Metar(self.raw)
            if parsed is not None:
                self.metar = parsed
            return (True, "Metar::parse: parsed")
        except MetarLib.ParserError as e:
            logger.debug(f"METAR failed to parse '{self.raw}': {e}")
        return (False, "Metar::parse: failed to parse")

    def getAtmap(self):
        if self.atmap is None and self.metar is not None:
            # self.atmap = ATMAP(obs=self.raw)
            self.atmap = ATMAP(metar=self.metar) # use already parsed version
        return self.atmap.bad_weather_classes() if self.atmap is not None else None


from .metar_avwx import MetarAVWX
from .metar_fpdb import MetarFPDB
from .metar_mesonet import MetarMesonet
from .metar_ogimet import MetarOgimet
