#  Python classes to format features for output to different channel requirements
#
import os
import logging

from emitpy.constants import FEATPROP, FLIGHT_DATABASE
from emitpy.parameters import MANAGED_AIRPORT_AODB

# Generic, yet another flavor of vanilla:
from .formatter import FormatterRaw, FormatterFlat, TrafficFormatter

# For X-Plane LiveTraffic and XPPlanes plugins:
from .formatter import AITFCFormatter, RTTFCFormatter, XPPlanesFormatter

logger = logging.getLogger("Formatter")

FORMATTERS = {
    "flat": ("Flattened JSON", FormatterFlat),
    "aitfc": ("X-Plane LiveTraffic", AITFCFormatter),
    "rttfc": ("X-Plane LiveTraffic", RTTFCFormatter),
    "xpplanes": ("XPPlanes shim", XPPlanesFormatter),
    "traffic": ("Traffic.py Library", TrafficFormatter),
    "raw": ("Raw JSON", FormatterRaw)
}

class Format:
    """
    Format an Emission for broadcasting.
    """

    def __init__(self, emit: "Emit", formatter = FormatterRaw):
        self.emit = emit
        self.formatter = formatter
        self.output = []
        self.version = 0


    @staticmethod
    def getCombo():
        """
        Returns a list of available formatters.
        """
        return [(k, v[0]) for k,v in FORMATTERS.items()]


    @staticmethod
    def getFormatter(name):
        """
        Returns Formatter from its name.

        :param      name:  The name
        :type       name:  { type_description }
        """
        return FORMATTERS[name][1] if name in FORMATTERS.keys() else FormatterRaw


    def format(self):
        """
        Formats each emission point.
        Effectively create a new list of (formatted) points.
        """
        if self.emit.scheduled_emit is None or len(self.emit.scheduled_emit) == 0:
            logger.warning("Format::format: no emission point")
            return (False, "Format::format no emission point")

        self.output = []  # reset if called more than once
        br = filter(lambda f: f.getProp(FEATPROP.BROADCAST.value), self.emit.scheduled_emit)
        bq = sorted(br, key=lambda f: f.getRelativeEmissionTime())
        self.output = list(map(self.formatter, bq))
        logger.debug(f':run: formatted {len(self.output)} / {len(self.emit.scheduled_emit)}, version {self.version}')
        self.version = self.version + 1
        return (True, "Format::format completed")


    def saveFile(self, overwrite: bool = False):
        """
        Save formatted points.

        :param      overwrite:  The overwrite
        :type       overwrite:  bool
        """
        basename = os.path.join(MANAGED_AIRPORT_AODB, FLIGHT_DATABASE)
        fileformat = self.formatter.FILE_EXTENSION
        ident = self.emit.getId()
        fn = f"{ident}-6-broadcast.{fileformat}"
        filename = os.path.join(basename, fn)
        if os.path.exists(filename) and not overwrite:
            logger.warning(f":save: file {filename} already exist, not saved")
            return (False, "Format::save file already exist")

        with open(filename, "w") as fp:
            for l in self.output:
                fp.write(str(l)+"\n")

        logger.debug(f":save: saved {fn}")
        return (True, "Format::save saved")
