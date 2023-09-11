"""
Flightplandb returns something like:
{
  "METAR": "KLAX 042053Z 26015KT 10SM FEW180 SCT250 25/17 A2994",
  "TAF": "TAF AMD KLAX 042058Z 0421/0524 26012G22KT P6SM SCT180 SCT250 FM050400 26007KT P6SM SCT200 FM050700 VRB05KT P6SM SCT007 SCT200 FM051800 23006KT P6SM SCT020 SCT180"
}
"""

import logging
import requests_cache

import flightplandb as fpdb

from emitpy.private import FLIGHT_PLAN_DATABASE_APIKEY
from emitpy.weather.aws import WebFetch


logger = logging.getLogger("FPDB")


class FPDBMetar(WebFetch):
	"""
	Loads METAR for ICAO from FlightplanDataBase.
	"""
	def __init__(self, icao: str):
		WebFetch.__init__(self, icao)

	def fetch(self):
		remote = None
		try:
			remote = fpdb.weather.fetch(icao=self.icao, key=FLIGHT_PLAN_DATABASE_APIKEY)
			if remote is not None and remote.METAR is not None:
				self.raw = remote.METAR
		except:
			remote = None
			logger.error("fetch: error fetching METAR, ignoring METAR", exc_info=True)

		if remote is not None and remote.METAR is not None:
			return (True, "FPDBMetar::fetch: fetched")
		return (False, "FPDBMetar::fetch: could not get metar")


class FPDBTaf(WebFetch):
	"""
	Loads METAR for ICAO from FlightplanDataBase.
	"""
	def __init__(self, icao: str):
		WebFetch.__init__(self, icao)

	def fetch(self):
		remote = None
		try:
			remote = fpdb.weather.fetch(icao=self.icao, key=FLIGHT_PLAN_DATABASE_APIKEY)
			if remote is not None and remote.TAF is not None:
				self.raw = remote.TAF
		except:
			remote = None
			logger.error("fetch: error fetching TAF, ignoring TAF", exc_info=True)

		if remote is not None and remote.METAR is not None:
			return (True, "FPDBTaf::fetch: fetched")
		return (False, "FPDBTaf::fetch: could not get taf")
