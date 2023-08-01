# Base class(es) for Weather transmission to Emitpy
# The Weather Engine is responsible for fetching airport weather and en route wind data for flights.
#
import logging
import importlib
import json
import os

from abc import ABC, abstractmethod
from datetime import datetime

from emitpy.parameters import WEATHER_DIR
from .weather_utils import normalize_dt

logger = logging.getLogger("WeatherEngine")


AIRPORT_WEATHER_DIR = os.path.join(WEATHER_DIR, "airports")


class Wind:
	# Shell class, used to get wind information for Emitpy

	def __init__(self, direction: float, speed: float):
		self.direction = direction
		self.speed = speed
		self.position = None  # tuple(float)
		self.moment: None

	def getInfo(self) -> dict:
		"""
		Returns weather information.
		"""
		return {
			"direction": self.direction,
			"speed": self.speed
		}

	def __str__(self):
		return json.dumps(self.getInfo())


class AirportWeather(ABC):
	# Abstract class, used to get airport weather information for Emitpy

	def __init__(self, icao: str, moment: datetime = None, engine = None):
		self.engine = engine

		self.type = None	# METAR, TAF, or other
		self.icao = icao
		self.requested_dt = moment if moment is not None else datetime.now().astimezone()
		self.requested_norm = normalize_dt(self.requested_dt)

		self.raw = None
		self.parsed = None

	def getInfo(self) -> dict:
		"""
		Returns weather information.
		"""
		return {
			"icao": self.icao,
			"date": self.requested_dt,
			"type": self.type,
			"raw": self.raw
		}

	@abstractmethod
	def summary(self):
		# Returns weather in a descriptive way, for debugging purpose only
		# Standard metar.string returns imperial units :-(.
		raise NotImplementedError

	@abstractmethod
	def get_wind(self) -> Wind:
		# Get overall wind at ground level
		# Returns None for wind direction if no wind or direction variable.
		# Returns wind speed, 0 if no wind.
		# Affects runway selection. Does not affect take-off and landing distances. (even if strong head winds.)
		raise NotImplementedError

	@abstractmethod
	def get_precipirations(self):
		# Returns cm of precipitation for the last hour (in cm of water).
		# Affects take-off and landing distances.
		raise NotImplementedError

	def save(self):
		if self.engine.redis is not None:
			return self.saveToCache()
		else:
			return self.saveFile()

	def load(self):
		if self.engine.redis is not None:
			return self.loadFromCache()
		else:
			return self.loadFile()

	def saveFileName(self):
		nowstr = self.cacheKeyName()
		return os.path.join(AIRPORT_WEATHER_DIR, self.icao + "-" + nowstr + "." + self.type.lower())

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
				return (True, "Metar::loadFile: loaded")
			except:
				logger.debug(f"problem reading from {fn}", exc_info=True)
				self.raw = None
			return (False, "Metar::loadFile: not loaded")

		logger.debug(f"file not found {fn}")
		return (False, "Metar::loadFile: not loaded")

	def cacheKeyName(self):
		return self.requested_norm.strftime('%Y%m-%d%H%MZ')

	def saveToCache(self):
		if self.raw is not None:
			prevdb = self.engine.redis.client_info()["db"]
			self.engine.redis.select(REDIS_DB.PERM.value)
			nowstr = self.cacheKeyName()
			metid = key_path(REDIS_DATABASE.METAR.value, self.raw[0:4], nowstr)
			if not self.engine.redis.exists(metid):
				self.engine.redis.set(metid, self.raw)
				self.engine.redis.select(prevdb)
				logger.debug(f"saved {metid}")
				return (True, "Metar::saveToCache: saved")
			else:
				self.engine.redis.select(prevdb)
				logger.warning(f"already exist {metid}")
		else:
			logger.warning(f"no metar to save")
		return (False, "Metar::saveToCache: not saved")

	def loadFromCache(self):
		if self.engine.redis is not None:
			nowstr = self.cacheKeyName()
			metid = REDIS_DATABASE.METAR.value + ":" + self.icao + ":" + nowstr
			if self.engine.redis.exists(metid):
				logger.debug(f"found {metid}")
				raw = self.engine.redis.get(metid)
				self.raw = raw.decode("UTF-8")
				return (True, "Metar::loadFromCache: loaded and parsed")
			else:
				logger.debug(f"not found {metid}")
		return (False, "Metar::loadFromCache: failed to load")



class WeatherEngine(ABC):
	"""
	Weather Engine is responsible for providing weather data to emitpy.
	Data consists of weather at departure, arrival (and alternate) airport,
	and wind data for the flight.
	"""
	def __init__(self, redis):
		self.redis = redis
		self.source = None
		self.source_date = None
		self.flight_id = None

		self.mkdirs()

	@classmethod
	def new(cls, redis):
		return cls(redis)


	def mkdirs(self, create: bool = True):
		# Weather sub-directories
		dirs = []
		dirs.append(os.path.join(WEATHER_DIR, "airports"))  # METAR and TAF
		dirs.append(os.path.join(WEATHER_DIR, "flights"))	# En-route bounding boxed winds for flights
		dirs.append(os.path.join(WEATHER_DIR, "gfs"))		# GFS
		for d in dirs:
			if not os.path.exists(d):
				logger.warning(f"directory {d} does not exist")
				if create:
					os.makedirs(d)
					logger.info(f"created directory {d}")

	@abstractmethod
	def get_airport_weather(self, icao: str, moment: datetime) -> AirportWeather:
		"""
		Get weather at airport locat
		"""
		raise NotImplementedError

	@abstractmethod
	def prepare_enroute_winds(self, flight) -> bool:
		# Filter and cache winds for flight
		raise NotImplementedError

	def forget_enroute_winds(self, flight):
		# Clear cached flight
		self.flight_id = None

	def has_enroute_winds(self, flight) -> bool:
		return self.flight_id == flight.getId()

	@abstractmethod
	def get_enroute_wind(self, lat, lon, alt, moment: datetime) -> Wind:
		"""
		Get En Route wind for flight. Flight movement points are passed here, with (lat, lon, alt)
		and an estimated time of passage at the point.
		This procedure retrieve winds (speed and direction) at the location for the requested time.
		Ultimately, it could be any position (on Earth) at any give time, if weather data can be found.
		A sophisticated optional "fall-back" mechanism does its best at finding data for the supplied position,
		or close by positions, at requested time or another close time.
		"""
		raise NotImplementedError
