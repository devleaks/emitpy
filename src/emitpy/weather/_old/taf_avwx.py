"""
A TAF is a weather forecast at a named location, usually an airport.
"""
import logging
from .taf import TAF
from avwx import Taf

logger = logging.getLogger("TAFAVWX")


class TAFAVWX(TAF):
    """
    Loads TAF for ICAO from AVWX.
    """
    def __init__(self, icao: str, redis = None):
        TAF.__init__(self, icao=icao, redis=redis)
        # For development
        if redis is not None:
            backend = requests_cache.RedisCache(host=REDIS_CONNECT["host"], port=REDIS_CONNECT["port"], db=2)
            requests_cache.install_cache(backend=backend)
        # else:
        #     requests_cache.install_cache()  # defaults to sqlite
        self.init()

    def fetch(self):
        taf = None
        try:
            taf = Taf(self.icao)
        except:
            taf = None
            logger.error("fetch: error fetching TAF, ignoring TAF", exc_info=True)
        if taf is not None and taf.raw is not None:
            self.raw = taf.raw
            logger.debug(f"{self.raw}")
            return self.parse()
        return (False, "TAFAVWX::fetch: could not get TAF")
