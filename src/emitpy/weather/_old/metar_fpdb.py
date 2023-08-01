"""
A METAR is a weather situation at a named location, usually an airport.
"""
import logging
import requests_cache

from .metar import Metar
import flightplandb as fpdb

from emitpy.parameters import REDIS_CONNECT
from emitpy.private import FLIGHT_PLAN_DATABASE_APIKEY

logger = logging.getLogger("MetarFPDB")


class MetarFPDB(Metar):
    """
    Loads cached METAR for ICAO or fetch **current** from flightplandatabase and cache it.
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
        metar = None
        try:
            metar = fpdb.weather.fetch(icao=self.icao, key=FLIGHT_PLAN_DATABASE_APIKEY)
        except:
            metar = None
            logger.error("fetch: error fetching METAR, ignoring METAR", exc_info=True)
        """
        Flightplandb returns something like:
        {
          "METAR": "KLAX 042053Z 26015KT 10SM FEW180 SCT250 25/17 A2994",
          "TAF": "TAF AMD KLAX 042058Z 0421/0524 26012G22KT P6SM SCT180 SCT250 FM050400 26007KT P6SM SCT200 FM050700 VRB05KT P6SM SCT007 SCT200 FM051800 23006KT P6SM SCT020 SCT180"
        }
        """
        if metar is not None and metar.METAR is not None:
            self.raw = metar.METAR
            logger.debug(f"{self.raw}")
            return self.parse()
        return (False, "MetarFPDB::fetch: could not get metar")
