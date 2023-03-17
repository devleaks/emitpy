"""
A METAR is a weather situation at a named location, usually an airport.
"""
import logging
from .metar import Metar
from avwx import Metar as MetarAVWX

logger = logging.getLogger("MetarAVWX")


class MetarAVWX(Metar):
    """
    Loads METAR for ICAO from AVWX.
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
            metar = Metar(self.icao)
        except:
            metar = None
            logger.error("fetch: error fetching METAR, ignoring METAR", exc_info=True)
        if metar is not None and metar.METAR is not None:
            self.raw = metar.raw
            logger.debug(f":fetch: {self.raw}")
            return self.parse()
        return (False, "MetarAVWX::fetch: could not get metar")
