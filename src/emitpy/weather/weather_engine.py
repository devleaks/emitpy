import logging
from abc import ABC, abstractmethod
from datetime import datetime
import importlib

logger = logging.getLogger("WeatherEngine")


class Wind:
	# Shell class, used to get wind information for Emitpy

	def __init__(self, direction: float, speed: float):
		self.direction = direction
		self.speed = speed

	def getInfo(self) -> dict:
		"""
		Returns weather information.
		"""
		return {
			"direction": self.direction,
			"speed": self.speed
		}


class AirportWeather(ABC):
	# Shell class, used to get airport weather information for Emitpy

	def __init__(self, icao: str):
		self.source = None
		self.icao = icao

	def getInfo(self) -> dict:
		"""
		Returns weather information.
		"""
		return {
			"icao": self.icao
		}

	@abstractmethod
	def get_wind(self) -> Wind:
		raise NotImplementedError

	@abstractmethod
	def get_precipirations(self):
		raise NotImplementedError


class WeatherEngine(ABC):

	def __init__(self, redis):
		self.redis = redis
		self._winds_prepared = False
		self._bbox = None
		self.moment = None
		self.source = None

	@classmethod
	def new(cls, redis):
		return cls(redis)

	@abstractmethod
	def get_airport_weather(self, icao: str, moment: datetime) -> AirportWeather:
		raise NotImplementedError

	@abstractmethod
	def prepare_enroute_winds(self, bbox: [float], moment: datetime) -> bool:
		self._winds_prepared = True
		self._bbox = bbox
		self.moment = moment
		return False

	def forget_enroute_winds(self, bbox: [float], moment: datetime):
		self._winds_prepared = False
		self._bbox = None
		self.moment = None

	def has_enroute_winds(self, bbox: [float], moment: datetime) -> bool:
		return self._winds_prepared and self._bbox == bbox and self.moment == moment

	@abstractmethod
	def get_enroute_wind(self, position: [float]) -> Wind:
		if self._winds_prepared:
			raise NotImplementedError
		return None
