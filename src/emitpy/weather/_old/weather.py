"""
Weather situation at a named location, usually an airport.
"""
import os
import logging
import importlib
from enum import Enum
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone

from emitpy.constants import REDIS_DATABASE, REDIS_DB
from emitpy.parameters import WEATHER_DIR
from emitpy.utils import key_path
from .atmap import ATMAP

logger = logging.getLogger("Weather")


def round_dt(dt, delta):
    # rounds datetime to delta after datetime.
    dtret = dt + (datetime.min - dt.replace(tzinfo=None)) % delta
#   logger.debug(f"{dt}=>{dtret}")
    return dtret

def normalize_dt(dt):
    # convert datetime to UTC and round it to half hour
    dtutc = dt.astimezone(tz=timezone.utc)
    dtret = round_dt(dtutc - timedelta(minutes=30), timedelta(minutes=30))
    logger.debug(f"{dt}: {dtutc}=>{dtret}")
    return dtret


class WEATHER_SOURCE(Enum):
    METAR = "METAR"
    TAF   = "TAF"
    SPECI = "SPECI"


class Weather(ABC):
    """
    Loads cached weather for ICAO location or fetch **current** from source.
    Parse the weather for the source and only report information of interest:
      - Wind direction (and speed if necessary)
      - Precipitation quantity (and type if necessary)
      - Description of weather, which may default to raw METAR/TAF string
    Answer the question: What was the weather like at the airport at the time of the movement? (take-off or landing)
    Can be used at the managed airport, or at the remote airport.
    Abstract class only implement caching (file or redis)
    """
    def __init__(self, icao: str, movement_datetime: datetime = datetime.now().astimezone(), redis = None):
        self.redis = redis

        self.icao = icao

        self.moment = movement_datetime     # Datetime of requested weather
        self.moment_norm = normalize_dt(self.moment)

        self.content_source = WEATHER_SOURCE.UNKNOWN
        self.content_parsed = None          # parsed metar/taf
        self.content_raw = None             # metar string/taf as fetched from remote server
        self.content_datetime = self.moment # Datetime of content
        self.content_ok = False

        self.atmap_capable = False
        self.atmap = None   # Eurocontrol ATMAP coefficients from METAR (and may be TAF in the future)

        # If we don't use redis, we need a folder to store weather information
        # File extension is type of content (from WEATHER_SOURCE Enum)
        if redis is None and not os.path.exists(WEATHER_DIR) or not os.path.isdir(WEATHER_DIR):
            logger.warning(f"no Metar directory {WEATHER_DIR}")


    # ####################################
    # Weather creation
    #
    @staticmethod
    def new(icao: str, movement_datetime: datetime = datetime.now().astimezone(), redis=None, method: str = "WeatherMETARAVWX"):
        """
        Create a new Weather information using the supplied fetch method.

        :param      icao:    The icao
        :type       icao:    str
        :param      redis:   The redis
        :type       redis:   { type_description }
        :param      method:  The method
        :type       method:  str
        """
        metarclasses = importlib.import_module(name=".weather.metar", package="emitpy")
        if hasattr(metarclasses, method):
            doit = getattr(metarclasses, method)
            return doit(icao, redis, movement_datetime)
        else:
            logger.warning(f"could not get Metar implementation {method}")
        return None

    # ####################################
    # Weather internals...
    #
    def init(self):
        r0 = self.load()
        if not r0[0]:  # it is ok for load to fail, if not found
            r1 = self.fetch()
            if r1[0]:
                r2 = self.save()
                if not r2[0]:
                    logger.warning(r2[1])
            else:
                logger.warning(r1[1])
        else:
            logger.warning(r0[1])

    def setDatetime(self, moment: datetime = datetime.now().astimezone()):
        self.moment = moment
        self.moment_norm = normalize_dt(self.moment)

        self.content_parsed = None          # clean parsed metar/taf
        self.content_raw = None             # clean metar string/taf as fetched from remote server
        self.content_datetime = self.moment # Datetime of content

        self.init()                         # fetch it

    def getInfo(self):
        return {
            "icao": self.icao,
            "date": self.moment_norm.isoformat(),
            "type": self.content_source.value,
            "raw": self.raw
        }

    def getDatetimeKey(self):
        """
        Gets the full data time for storage. METAR only have latest DDHHMM, with no year or month.
        So we add them to Redis keys and filenames.
        """
        return self.moment_norm.strftime('%Y%m-%d%H%MZ')

    def getKey(self):
        nowstr = self.getDatetimeKey()
        return key_path(REDIS_DATABASE.METAR.value, self.content_source.value.lower(), self.icao, nowstr)

    def getFilename(self):
        nowstr = self.getDatetimeKey()
        return os.path.join(WEATHER_DIR, self.icao + "-" + nowstr + "." + self.content_source.value.lower())

    def save(self):
        if self.content_ok:
            if self.redis is not None:
                return self.saveToCache()
            else:
                return self.saveFile()
        else:
            return (False, "Weather::save: no weather to save")

    def load(self):
        if self.redis is not None:
            return self.loadFromCache()
        else:
            return self.loadFile()

    def saveFile(self):
        if self.raw is not None:
            fn = self.getFilename()
            if not os.path.exists(fn):
                logger.warning(f"saving into {fn} '{self.raw}'")
                with open(fn, "w") as outfile:
                    outfile.write(self.raw)
            else:
                logger.warning(f"already exist {fn}")
            return (True, "Weather::saveFile: saved")
        return (False, "Weather::saveFile: no weather to save")

    def loadFile(self):
        fn = self.getFilename()
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
                return (True, "Weather::loadFile: loaded and parsed")
            return (False, "Weather::loadFile: not loaded")
        else:
            logger.debug(f"file not found {fn}")
        return (False, "Weather::loadFile: not loaded")

    def saveToCache(self):
        if self.raw is not None:
            prevdb = self.redis.client_info()["db"]
            self.redis.select(REDIS_DB.PERM.value)
            nowstr = self.getDatetimeKey()
            metid = key_path(REDIS_DATABASE.METAR.value, self.raw[0:4], nowstr)
            if not self.redis.exists(metid):
                self.redis.set(metid, self.raw)
                self.redis.select(prevdb)
                logger.debug(f"saved {metid}")
                return (True, "Weather::saveToCache: saved")
            else:
                self.redis.select(prevdb)
                logger.warning(f"already exist {metid}")
        else:
            logger.warning(f"no metar to save")
        return (False, "Weather::saveToCache: not saved")

    def loadFromCache(self):
        if self.redis is not None:
            metid = self.getKey()
            if self.redis.exists(metid):
                logger.debug(f"found {metid}")
                raw = self.redis.get(metid)
                self.raw = raw.decode("UTF-8")
                if self.raw is not None:
                    return self.parse()
                    return (True, "Weather::loadFromCache: loaded and parsed")
                return (False, "Weather::loadFromCache: failed to get")
            else:
                logger.debug(f"not found {metid}")
        return (False, "Weather::loadFromCache: failed to load")


    def getAtmap(self):
        if self.atmap_capable:
            if self.content_raw is not None:
                self.atmap = ATMAP(metar=self.content_raw) # use already parsed version
        if self.atmap is not None:
            return self.atmap.bad_weather_classes() if self.atmap is not None else None
        return None


    # ####################################
    # Weather Emitpy Interface
    #
    @abstractmethod
    def fetch(self):
        """
        Fetches the METAR from its source.
        """
        raise NotImplementedError("Weather::fetch: abstract method: Please Implement this method")

    @abstractmethod
    def parse(self):
        """
        Clear protected parsing of Metar.
        If parsing succeeded, result is kept
        """
        raise NotImplementedError("Weather::parse: abstract method: Please Implement this method")

    @abstractmethod
    def getWindDirection(self, moment: datetime = None):
        """
        Returns wind direction if any, or None if no wind or multiple directions.
        Used at Airport to determine runways in use.
        """
        raise NotImplementedError("Weather::parse: abstract method: Please Implement this method")

    @abstractmethod
    def getWindSpeed(self, moment: datetime = None, alt: int = Nnoe):
        """
        Returns wind direction if any, or None if no wind or multiple directions.
        Used at Airport to determine runways in use.
        """
        raise NotImplementedError("Weather::parse: abstract method: Please Implement this method")

    @abstractmethod
    def getPrecipitation(self, moment: datetime = None):
        """
        Returns amount of precipitations in CM of water. No difference between water, ice, snow, hail...
        Used in flights to calculate landing distance of an aircraft.
        """
        raise NotImplementedError("Weather::parse: abstract method: Please Implement this method")

    @abstractmethod
    def getDetail(self):
        raise NotImplementedError("Weather::parse: abstract method: Please Implement this method")

    @abstractmethod
    def getSummary(self):
        raise NotImplementedError("Weather::parse: abstract method: Please Implement this method")
