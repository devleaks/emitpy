"""
A METAR is a weather situation at a named location, usually an airport.
"""
import os
import re
import json
import logging
import requests_cache
import redis
import urllib.request

from datetime import datetime, timedelta, timezone
from metar import Metar as MetarLib

import flightplandb as fpdb

# from metar import Metar as MetarLib

from ..constants import METAR_DATABASE
from ..parameters import AODB_DIR

from ..private import FLIGHT_PLAN_DATABASE_APIKEY

METAR_DIR = os.path.join(AODB_DIR, METAR_DATABASE)

logger = logging.getLogger("Metar")


def round_dt(dt, delta):  # rounds date to delta after date.
    return dt + (datetime.min - dt.replace(tzinfo=None)) % delta

def normalize_dt(dt):
    dtutc = dt.astimezone(tz=timezone.utc)
    dtret = round_dt(dtutc - timedelta(minutes=30), timedelta(minutes=60))
    logger.debug(f":normalize_dt: {dt}: {dtutc}=>{dtret}")
    return dtret


class MetarOjb(object):
    def __init__(self, metar: str):
        self.METAR = metar
    def _to_api_dict(self):
        return {"METAR": self.METAR}

class Metar:
    """
    Loads cached METAR for ICAO or fetch **current** from flightplandatabase.
    """

    USE_REDIS = False

    def __init__(self, icao: str, moment: datetime = None, use_redis: bool = False):
        self.icao = icao
        self.moment = moment
        self.raw = None
        self.metar = None
        self.api = fpdb.FlightPlanDB(FLIGHT_PLAN_DATABASE_APIKEY)

        # For development
        requests_cache.install_cache()

        if use_redis:  # sets it once and for all
            Metar.USE_REDIS = use_redis

        self.moment_norm = normalize_dt(self.moment if self.moment is not None else datetime.now())

        self.init()


    def init(self):
        if Metar.USE_REDIS:
            self.loadDB()
            if self.raw is None:
                self.fetch()
                self.saveDB()
        else:
            self.load()
            if self.raw is None:
                self.fetch()
                self.save()


    def fetch(self):
        if self.moment is not None:
            ret = self.fetchHistoricalMetar()
            if ret[0]:
                return ret
            logger.warning(f":fetch: could not get historical metar, trying for now")
        # if could not get historical metar, get latest one
        metar = self.api.weather.fetch(icao=self.icao)
        if metar is not None and metar.METAR is not None:
            self.raw = metar
            if self.raw is not None:
                logger.debug(f":fetch: {self.raw.METAR},")
                self.parse(self.raw.METAR)
                return (True, "Metar::fetch:got metar")
        return (False, "Metar::fetch: could not get metar")


    def save(self):
        metid = "*ERROR*"
        fn = "*ERROR*"
        if self.raw is not None:
            metid = self.raw.METAR[0:4] + '-' + self.raw.METAR[5:12]
            fn = os.path.join(METAR_DIR, metid + ".json")
            if not os.path.exists(fn):
                with open(fn, "w") as outfile:
                    json.dump(self.raw._to_api_dict(), outfile)


    def load(self):
        nowstr = self.moment_norm.strftime('%d%H%MZ')
        fn = os.path.join(METAR_DIR, self.icao + "-" + nowstr + ".json")
        logger.debug(f":load: trying {fn}")
        if os.path.exists(fn):
            with open(fn, "r") as fp:
                self.raw = json.load(fp)
            if self.raw is not None:
                self.parse(self.raw["METAR"])
            logger.debug(f":load: found {fn}")
        else:
            logger.debug(f":load: not found {fn}")


    def saveDB(self):
        if self.raw is not None:
            metid = "METAR:" + self.raw.METAR[0:4] + ':' + self.raw.METAR[5:12]
            r = redis.Redis()
            if not r.exists(metid):
                r.set(metid, json.dumps(self.raw._to_api_dict()))


    def loadDB(self):
        nowstr = self.moment_norm.strftime('%d%H%MZ')
        metid = "METAR:" + self.icao + ":" + nowstr
        logger.debug(f":loadDB: trying {metid}")
        r = redis.Redis()
        if r.exists(metid):
            raw = r.get(metid)
            self.raw = json.loads(raw.decode("UTF-8"))
            if self.raw is not None:
                self.parse(self.raw["METAR"])
            logger.debug(f":loadDB: loaded {metid}")
        else:
            logger.debug(f":loadDB: not found {metid}")


    def get(self):
        return None if self.raw is None else self.raw["METAR"]


    def parse(self, metar: str):
        parsed = None
        try:
            parsed = MetarLib.Metar(metar)
        except MetarLib.ParserError as e:
            logger.debug(f":load: METAR failed to parse '{metar}': {e.message}")
            parsed = None

        if parsed is not None:
            self.metar = parsed

    def fetchHistoricalMetar(self):
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

        logger.debug(f":fetchHistoricalMetar: {url}")
        #with open("/Users/pierre/Developer/oscars/emitpy/src/emitpy/airspace/result.txt", "r") as response:  # urllib.request.urlopen(url) as response:
        with urllib.request.urlopen(url) as response:
            txt = response.read()  # .decode("UTF-8")
            # logger.debug(f":fetchHistoricalMetar: {txt}")
            # 201903312300 METAR OTHH 312300Z
            start = f"{nowstr2} METAR {self.icao} {nowstr}"
            metar = None
            for line in re.findall(start+"(.*)", txt):
                 metar = start+line
            # logger.debug(f":fetchHistoricalMetar: search for '{start}(.*)': {metar}")

        if metar is None:
            return (False, "failed to get historical metar")

        self.raw = MetarOjb(metar=metar[len(nowstr2)+7:-1])
        self.parse(self.raw.METAR)

        return (True, "Metar::fetchHistoricalMetar: got historical metar")

