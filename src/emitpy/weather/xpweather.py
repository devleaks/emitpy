import logging

from datetime import datetime

from .weather_engine import WeatherEngine, AirportWeather, Wind

logger = logging.getLogger("XPWeatherEngine")


class XPAirportWeather(AirportWeather):
	# Shell class, used to get airport weather information for Emitpy

	def __init__(self, icao: str, source):

		AirportWeather.__init__(self, icao=icao)

		self.source = None
		self.icao = icao

	def getInfo(self) -> dict:
		"""
		Returns weather information.
		"""
		return {
			"source": self.source,
			"icao": self.icao
		}

	def get_wind(self) -> Wind:
		return None

	def get_precipirations(self):
		return 0


class XPWeatherEngine(WeatherEngine):

	def __init__(self, redis):

		WeatherEngine.__init__(self, redis)


	def has_cruise_winds(self, bbox: [float], moment: datetime):
		return self._winds_prepared and self._bbox == bbox and self.moment == moment

	def get_airport_weather(self, icao: str, moment: datetime):
		return XPAirportWeather(icao=icao, source="test")

	def prepare_enroute_winds(self, bbox: [float], moment: datetime):
		self._winds_prepared = True
		self._bbox = bbox
		self.moment = moment

	def get_enroute_wind(self, position: [float]):
		if self._winds_prepared:
			pass
		return None
