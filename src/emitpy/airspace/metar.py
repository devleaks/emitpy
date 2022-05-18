"""
A METAR is a weather situation at a named location, usually an airport.
"""
import os
import re
import json
import logging
import requests_cache
import urllib.request
import importlib

from datetime import datetime, timedelta, timezone
from metar import Metar as MetarLib

import flightplandb as fpdb

# from metar import Metar as MetarLib

from emitpy.constants import METAR_DATABASE, REDIS_DATABASE
from emitpy.parameters import AODB_DIR, REDIS_CONNECT, USE_REDIS

from emitpy.private import FLIGHT_PLAN_DATABASE_APIKEY

logger = logging.getLogger("Metar")

METAR_DIR = os.path.join(AODB_DIR, METAR_DATABASE)


def round_dt(dt, delta):  # rounds date to delta after date.
    return dt + (datetime.min - dt.replace(tzinfo=None)) % delta

def normalize_dt(dt):
    dtutc = dt.astimezone(tz=timezone.utc)
    dtret = round_dt(dtutc - timedelta(minutes=30), timedelta(minutes=60))
    logger.debug(f":normalize_dt: {dt}: {dtutc}=>{dtret}")
    return dtret


class Metar:
    """
    Loads cached METAR for ICAO or fetch **current** from flightplandatabase.
    """
    def __init__(self, icao: str, redis = None):
        self.icao = icao
        self.moment = datetime.now()
        self.moment_norm = normalize_dt(self.moment)
        self.metar = None   # parsed metar
        self.raw = None     # metar string
        self.redis = redis


    @staticmethod
    def new(icao: str, redis=None, method: str = "MetarFPDB"):
        metarclasses = importlib.import_module(name=".airspace.metar", package="emitpy")
        if hasattr(metarclasses, method):
            doit = getattr(metarclasses, method)
            return doit(icao, redis)
        else:
            logger.warning(f":__init__: could not get Metar implementation {method}")
        return None


    def init(self):
        self.load()
        if self.raw is None:
            self.fetch()
            self.save()


    def setDatetime(self, moment: datetime = datetime.now()):
        self.moment = moment
        self.moment_norm = normalize_dt(self.moment)
        self.metar = None
        self.raw = None
        self.init()


    def get(self):
        return self.raw


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


    def load(self):
        if self.redis is not None:
            return self.loadFromCache()
        nowstr = self.moment_norm.strftime('%d%H%MZ')
        fn = os.path.join(METAR_DIR, self.icao + "-" + nowstr + ".json")
        logger.debug(f":load: trying {fn}")
        if os.path.exists(fn):
            with open(fn, "r") as fp:
                self.raw = read(fp)
            if self.raw is not None:
                logger.debug(f":load: found {fn}")
                return self.parse(self.raw["METAR"])
            return (False, "Metar::load: not loaded")
        else:
            logger.debug(f":load: not found {fn}")


    def save(self):
        if self.redis is not None:
            if self.raw is not None:
                nowstr = self.getFullDT()
                metid = REDIS_DATABASE.METAR.value + ":" + self.raw[0:4] + ':' + nowstr
                if not self.redis.exists(metid):
                    self.redis.set(metid, self.raw)
                    return (True, "Metar::save: saved")
                else:
                    logger.warning(f":save: already exist {metid}")
            else:
                logger.warning(f":save: no metar to save")
        else:
            return self.saveFile()
        return (False, "Metar::save: not saved")


    def saveFile(self):
        metid = "*ERROR*"
        fn = "*ERROR*"
        if self.raw is not None:
            metid = self.raw[0:4] + '-' + self.raw[5:12]
            fn = os.path.join(METAR_DIR, metid + ".json")
            if not os.path.exists(fn):
                with open(fn, "w") as outfile:
                    print(self.raw, outfile)
            else:
                logger.warning(f":save: already exist {fn}")
            return (True, "Metar::save: saved")
        return (False, "Metar::save: not saved")


    def loadFromCache(self):
        if self.redis is not None:
            nowstr = self.getFullDT()
            metid = REDIS_DATABASE.METAR.value + ":" + self.icao + ":" + nowstr
            logger.debug(f":loadFromCache: trying {metid}")
            if self.redis.exists(metid):
                raw = self.redis.get(metid)
                self.raw = raw.decode("UTF-8")
                if self.raw is not None:
                    return self.parse()
                return (False, "Metar::loadFromCache: failed to get")
            else:
                logger.debug(f":loadFromCache: not found {metid}")
        return (False, "Metar::loadFromCache: failed to load")


    def getFullDT(self):
        """
        Gets the full data time for storage. METAR only have latest DDHHMM, with no year or month.
        """
        return self.moment_norm.strftime('%Y%m%d%H%MZ')


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



class MetarFPDB(Metar):
    """
    Loads cached METAR for ICAO or fetch **current** from flightplandatabase.
    """

    def __init__(self, icao: str, redis = None):
        Metar.__init__(self, icao=icao, redis=redis)
        self.api = fpdb.FlightPlanDB(FLIGHT_PLAN_DATABASE_APIKEY)
        # For development
        if USE_REDIS:
            backend = requests_cache.RedisCache(host=REDIS_CONNECT["host"], port=REDIS_CONNECT["port"], db=2)
            requests_cache.install_cache(backend=backend)
        else:
            requests_cache.install_cache()  # defaults to sqlite
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
        metar = self.api.weather.fetch(icao=self.icao)
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
        with urllib.request.urlopen(url) as response:
            txt = response.read().decode("UTF-8")
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
        logger.debug(f":fetch: metar '{self.raw}'")
        return self.parse()
