# Base class(es) for Weather transmission to Emitpy
# The Weather Engine is responsible for fetching airport weather and en route wind data for flights.
#
import logging
import importlib
import json

from abc import ABC, abstractmethod
from datetime import datetime

logger = logging.getLogger("WeatherEngine")


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

	def __init__(self, icao: str, moment: datetime = None):
		self.type = None	# METAR, TAF, or other
		self.source = None  # filename of source file
		self.icao = icao

	def getInfo(self) -> dict:
		"""
		Returns weather information.
		"""
		return {
			"icao": self.icao
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

	## Add method to cache it
	## Add method to retrieve from cache


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

	@classmethod
	def new(cls, redis):
		return cls(redis)

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
