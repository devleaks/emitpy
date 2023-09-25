from abc import ABC, abstractmethod

from emitpy.weather.utils import normalize_dt


class WebFetch(ABC):
    """
    Loads METAR for ICAO from AVWX.
    """

    def __init__(self, icao: str, moment=None):
        self.icao = icao
        self.moment = moment  # this is for "past" METAR
        self.moment_norm = None
        if self.moment is not None:
            self.moment_norm = normalize_dt(self.moment)
        self.raw = None

    def succeeded(self) -> bool:
        return self.raw is not None

    @abstractmethod
    def fetch(self):
        return (False, "WebFetch::fetch: not implemented")


from .avwx import AVWXMetar, AVWXTaf
from .fpdb import FPDBMetar, FPDBTaf
