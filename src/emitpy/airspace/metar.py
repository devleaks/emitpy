"""
A METAR is a weather situation at a named location, usually an airport.
"""
import os
import re
import logging
import importlib
from datetime import datetime, timedelta, timezone

import requests_cache
import requests

from metar import Metar as MetarLib

import flightplandb as fpdb

# from metar import Metar as MetarLib

from emitpy.constants import REDIS_DATABASE, REDIS_DB
from emitpy.parameters import METAR_DIR, REDIS_CONNECT
from emitpy.utils import key_path
from .atmap import ATMAP
from emitpy.private import FLIGHT_PLAN_DATABASE_APIKEY

logger = logging.getLogger("Metar")


def round_dt(dt, delta):  # rounds date to delta after date.
    return dt + (datetime.min - dt.replace(tzinfo=None)) % delta

def normalize_dt(dt):
    dtutc = dt.astimezone(tz=timezone.utc)
    dtret = round_dt(dtutc - timedelta(minutes=30), timedelta(minutes=30))
    logger.debug(f":normalize_dt: {dt}: {dtutc}=>{dtret}")
    return dtret


class Metar:
    """
    Loads cached METAR for ICAO or fetch **current** from flightplandatabase.
    """
    def __init__(self, icao: str, redis = None):
        self.icao = icao
        self.moment = datetime.now().astimezone()
        self.moment_norm = normalize_dt(self.moment)
        self.metar = None   # parsed metar
        self.raw = None     # metar string
        self.atmap = None   # Eurocontrol ATMAP coefficient
        self.redis = redis

        # this is now checked/created in managedairport at startup
        # if redis is None:
        #     pathlib.Path(METAR_DIR).mkdir(parents=True, exist_ok=True)
        if redis is None and not os.path.exists(METAR_DIR) or  not os.path.isdir(METAR_DIR):
            logger.warning(f":__init__: no Metar directory {METAR_DIR}")


    @staticmethod
    def new(icao: str, redis=None, method: str = "MetarFPDB"):
        metarclasses = importlib.import_module(name=".airspace.metar", package="emitpy")
        if hasattr(metarclasses, method):
            doit = getattr(metarclasses, method)
            return doit(icao, redis)
        else:
            logger.warning(f":new: could not get Metar implementation {method}")
        return None


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


    def hasMetar(self):
        return self.metar is not None


    def getInfo(self):
        return {
            "icao": self.icao,
            "date": self.moment_norm.isoformat(),
            "metar": self.raw
        }


    def fetch(self):
        """
        Fetches the metar from a source.
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
                logger.warning(f":saveFile: saving into {fn} '{self.raw}'")
                with open(fn, "w") as outfile:
                    outfile.write(self.raw)
            else:
                logger.warning(f":saveFile: already exist {fn}")
            return (True, "Metar::saveFile: saved")
        return (False, "Metar::saveFile: no METAR to saved")

    def loadFile(self):
        fn = self.saveFileName()
        if os.path.exists(fn):
            logger.debug(f":loadFile: found {fn}")
            try:
                with open(fn, "r") as fp:
                    self.raw = fp.readline()
            except:
                logger.debug(f":loadFile: problem reading from {fn}", exc_info=True)
                self.raw = None

            if self.raw is not None:
                return self.parse()
                return (True, "Metar::loadFile: loaded and parsed")
            return (False, "Metar::loadFile: not loaded")
        else:
            logger.debug(f":loadFile: file not found {fn}")
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
                logger.debug(f":saveToCache: saved {metid}")
                return (True, "Metar::saveToCache: saved")
            else:
                self.redis.select(prevdb)
                logger.warning(f":saveToCache: already exist {metid}")
        else:
            logger.warning(f":saveToCache: no metar to save")
        return (False, "Metar::saveToCache: not saved")

    def loadFromCache(self):
        if self.redis is not None:
            nowstr = self.cacheKeyName()
            metid = REDIS_DATABASE.METAR.value + ":" + self.icao + ":" + nowstr
            if self.redis.exists(metid):
                logger.debug(f":loadFromCache: found {metid}")
                raw = self.redis.get(metid)
                self.raw = raw.decode("UTF-8")
                if self.raw is not None:
                    return self.parse()
                    return (True, "Metar::loadFromCache: loaded and parsed")
                return (False, "Metar::loadFromCache: failed to get")
            else:
                logger.debug(f":loadFromCache: not found {metid}")
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
            logger.debug(f":load: METAR failed to parse '{self.raw}': {e}")
        return (False, "Metar::parse: failed to parse")


    def getAtmap(self):
        if self.atmap is None:
            self.atmap = ATMAP(obs=self.raw)
        return self.atmap.bad_weather_classes() if self.atmap is not None else None


class MetarFPDB(Metar):
    """
    Loads cached METAR for ICAO or fetch **current** from flightplandatabase.
    """

    def __init__(self, icao: str, redis = None):
        Metar.__init__(self, icao=icao, redis=redis)
        # For development
        if redis is not None:
            backend = requests_cache.RedisCache(host=REDIS_CONNECT["host"], port=REDIS_CONNECT["port"], db=2)
            requests_cache.install_cache(backend=backend)
        # else:
        #     requests_cache.install_cache()  # defaults to sqlite
        self.init()


    def fetch(self):
        """
        Fetches the object.
        Flightplandb returns something like:
        {
          "METAR": "KLAX 042053Z 26015KT 10SM FEW180 SCT250 25/17 A2994",
          "TAF": "TAF AMD KLAX 042058Z 0421/0524 26012G22KT P6SM SCT180 SCT250 FM050400 26007KT P6SM SCT200 FM050700 VRB05KT P6SM SCT007 SCT200 FM051800 23006KT P6SM SCT020 SCT180"
        }
        """
        metar = fpdb.weather.fetch(icao=self.icao, key=FLIGHT_PLAN_DATABASE_APIKEY)
        if metar is not None and metar.METAR is not None:
            self.raw = metar.METAR
            logger.debug(f":fetch: {self.raw}")
            return self.parse()
        return (False, "MetarFPDB::fetch: could not get metar")


class MetarHistorical(Metar):
    """
    Wrapper to maintain symmetry with current metar
    """
    def __init__(self, icao: str, redis = None):
        Metar.__init__(self, icao=icao, redis=redis)


    def fetch(self):
        """
        https://www.ogimet.com/display_metars2.php?lang=en&lugar=OTHH&tipo=SA&ord=REV&nil=SI&fmt=txt&ano=2019&mes=04&day=13&hora=07&anof=2019&mesf=04&dayf=13&horaf=07&minf=59&send=send      ==>
        201904130700 METAR OTHH 130700Z 29012KT 3500 TSRA FEW015 SCT030 FEW040CB OVC100 21/17 Q1011 NOSIG=
        """
        yr = self.moment_norm.strftime("%Y")
        mo = self.moment_norm.strftime("%m")
        dy = self.moment_norm.strftime("%d")
        hr = self.moment_norm.strftime("%H")
        nowstr = self.moment_norm.strftime('%d%H%MZ')
        nowstr2 = self.moment_norm.strftime('%Y%m%d%H%M')

        url = f"https://www.ogimet.com/display_metars2.php?lang=en&lugar={self.icao}&tipo=SA&ord=REV&nil=SI&fmt=txt"
        url = url + f"&ano={yr}&mes={mo}&day={dy}&hora={hr}&anof={yr}&mesf={mo}&dayf={dy}&horaf={hr}&minf=59&send=send"

        logger.debug(f":fetch: url={url}")
        #with open("/Users/pierre/Developer/oscars/emitpy/src/emitpy/airspace/result.txt", "r") as response:  # urllib.request.urlopen(url) as response:

        response = requests.get(url, cookies={'cookieconsent_status': 'dismiss'})
        txt = response.text

        # with urllib.request.urlopen(url) as response:
        #     txt = response.read().decode("UTF-8")
        logger.debug(f":fetch: {txt}")
        # 201903312300 METAR OTHH 312300Z
        start = f"{nowstr2} METAR {self.icao} {nowstr}"
        logger.debug(f":fetch: start '{start}'")
        metar = None
        for line in re.findall(start+"(.*)", txt):
             metar = start+line
            # logger.debug(f":fetchHistoricalMetar: search for '{start}(.*)': {metar}")

        if metar is None:
            return (False, "MetarHistorical::fetch: failed to get historical metar")

        self.raw = metar[len(nowstr2)+7:-1]
        logger.debug(f":fetch: historical metar {self.moment_norm} '{self.raw}'")
        return self.parse()
