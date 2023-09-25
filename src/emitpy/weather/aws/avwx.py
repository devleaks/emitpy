"""
A METAR is a weather situation at a named location, usually an airport.
"""
import logging

from avwx import Metar, Taf

from emitpy.weather.aws import WebFetch


logger = logging.getLogger("AVWX")


class AVWXMetar(WebFetch):
    """
    Loads METAR for ICAO from AVWX.
    """

    def __init__(self, icao: str):
        WebFetch.__init__(self, icao)

    def fetch(self):
        metar = None
        try:
            remote = Metar(self.icao)
            print(">>>>>>>", self.icao, remote)
            remote.update()
            self.raw = remote.raw
            logger.debug(f"{self.raw}")
            return (True, "AVWXMetar::fetch: fetched")
        except:
            logger.error("error fetching METAR, ignoring METAR", exc_info=True)
        return (False, "AVWXMetar::fetch: could not get metar")


class AVWXTaf(WebFetch):
    """
    Loads TAF for ICAO from AVWX.
    """

    def __init__(self, icao: str):
        WebFetch.__init__(self, icao)

    def fetch(self):
        metar = None
        try:
            remote = Taf(self.icao)
            remote.update()
            self.raw = remote.raw
            logger.debug(f"{self.raw}")
            return (True, "AVWXTaf::fetch: fetched")
        except:
            logger.error("error fetching TAF, ignoring TAF", exc_info=True)
        return (False, "AVWXTaf::fetch: could not get metar")
