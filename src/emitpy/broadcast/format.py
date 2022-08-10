#  Python classes to format features for output to different channel requirements
#
import os
import logging

from emitpy.constants import FEATPROP, FLIGHT_DATABASE
from emitpy.parameters import MANAGED_AIRPORT_AODB

from .formatter import Formatter, FormatterFlat, TrafficFormatter, LiveTrafficFormatter, XPPlanesFormatter

logger = logging.getLogger("Formatter")

FORMATTERS = {
    "flat": ("Flattened JSON", FormatterFlat),
    "lt": ("X-Plane LiveTraffic", LiveTrafficFormatter),
    "traffic": ("Traffic.py Library", TrafficFormatter),
    "xpplane": ("XPPlanes shim", XPPlanesFormatter),
    "raw": ("Raw JSON", Formatter)
}

class Format:

    def __init__(self, emit: "Emit", formatter: Formatter):
        self.emit = emit
        self.formatter = formatter
        self.output = []
        self.version = 0


    @staticmethod
    def getCombo():
        return [(k, v[0]) for k,v in FORMATTERS.items()]


    @staticmethod
    def getFormatter(name):
        return FORMATTERS[name][1] if name in FORMATTERS.keys() else Formatter


    def format(self):
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
        basename = os.path.join(MANAGED_AIRPORT_AODB, FLIGHT_DATABASE)
        fileformat = self.formatter.FILE_EXTENTION
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
        return (False, "Format::save saved")
