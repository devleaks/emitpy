#  Python classes to format features for output to different channel requirements
#
import os
import logging
import json

from emitpy.constants import FEATPROP, REDIS_DATABASES, REDIS_DATABASE
from emitpy.geo import asFeature
from turf import FeatureCollection
from emitpy.parameters import MANAGED_AIRPORT_AODB

# Generic, yet another flavor of vanilla:
from .formatter import FormatterRaw, FormatterFlat, FormatterWire, TrafficFormatter

# For X-Plane LiveTraffic and XPPlanes plugins:
from .formatter import AITFCFormatter, RTTFCFormatter, XPPlanesFormatter

logger = logging.getLogger("Format")

FORMATTERS = {
    "flat": ("Flattened JSON", FormatterFlat),
    "aitfc": ("X-Plane LiveTraffic", AITFCFormatter),
    "rttfc": ("X-Plane LiveTraffic", RTTFCFormatter),
    "xpplanes": ("XPPlanes shim", XPPlanesFormatter),
    "traffic": ("Traffic.py Library", TrafficFormatter),
    "wire": ("Message formatter", FormatterWire),
    "raw": ("Raw JSON", FormatterRaw),  # default, should always be available
}


class Format:
    """
    Format an Emission for broadcasting.
    """

    def __init__(self, emit: "Emit", formatter=FormatterRaw):
        self.emit = emit
        self.formatter = formatter
        self.output = []
        self.version = 0

    @staticmethod
    def getCombo():
        """
        Returns a list of available formatters.
        """
        return [(k, v[0]) for k, v in FORMATTERS.items()]

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
        emit_points = self.emit.getScheduledPoints()
        if emit_points is None or len(emit_points) == 0:
            logger.warning("Format::format: no emission point")
            return (False, "Format::format no emission point")

        self.output = []  # reset if called more than once
        br = filter(lambda f: f.getProp(FEATPROP.BROADCAST), emit_points)
        bq = sorted(br, key=lambda f: f.getRelativeEmissionTime())
        self.output = list(map(self.formatter, bq))
        logger.debug(
            f"formatted {len(self.output)} / {len(emit_points)}, version {self.version}"
        )
        self.version = self.version + 1
        return (True, "Format::format completed")

    def saveFile(self, overwrite: bool = False):
        """
        Save formatted points.

        :param      overwrite:  The overwrite
        :type       overwrite:  bool
        """
        db = (
            REDIS_DATABASES[self.emit.emit_type]
            if self.emit.emit_type in REDIS_DATABASES.keys()
            else REDIS_DATABASE.UNKNOWN.value
        )
        basename = os.path.join(MANAGED_AIRPORT_AODB, db)
        # fileformat = self.formatter.FILE_EXTENSION
        ident = self.emit.getId()
        fn = f"{ident}-6-broadcast.json"
        filename = os.path.join(basename, fn)
        if os.path.exists(filename) and not overwrite:
            logger.warning(f"file {filename} already exist, not saved")
            return (False, "Format::save file already exist")

        with open(filename, "w") as fp:
            for l in self.output:
                fp.write(str(l) + "\n")
        logger.debug(f"saved {fn}")

        # ==============================
        # ONLY WORKS FOR RAW FORMATTER
        # ==============================
        fn = f"{ident}-6-broadcast.geojson"
        filename = os.path.join(basename, fn)
        if os.path.exists(filename) and not overwrite:
            logger.warning(f"file {filename} already exist, not saved")
            return (False, "Format::save file already exist")

        with open(filename, "w") as fp:
            fc = FeatureCollection(
                features=[asFeature(json.loads(str(f))) for f in self.output]
            )
            json.dump(fc.to_geojson(), fp)
        logger.debug(f"saved {fn}")
        # ==============================

        return (True, "Format::save saved")


class FormatMessage(Format):
    def __init__(self, emit: "Emit", formatter=FormatterWire):
        Format.__init__(self, emit=emit, formatter=formatter)

    def format(self):
        """
        Formats each emission point.
        Effectively create a new list of (formatted) points.
        """
        messages = self.emit.getMessages()

        if messages is None or len(messages) == 0:
            logger.warning("no message")
            return (False, "FormatMessage::format no message")

        self.output = []  # reset if called more than once
        br = filter(lambda f: f.getAbsoluteEmissionTime(), messages)
        bq = sorted(br, key=lambda f: f.getAbsoluteEmissionTime())
        self.output = list(map(self.formatter, bq))
        logger.debug(
            f"formatted {len(self.output)} / {len(messages)} messages, version {self.version}"
        )
        self.version = self.version + 1
        return (True, "FormatMessage::format completed")

    def saveFile(self, overwrite: bool = False):
        """
        Save formatted points.

        :param      overwrite:  The overwrite
        :type       overwrite:  bool
        """
        db = (
            REDIS_DATABASES[self.emit.emit_type]
            if self.emit.emit_type in REDIS_DATABASES.keys()
            else REDIS_DATABASE.UNKNOWN.value
        )
        basename = os.path.join(MANAGED_AIRPORT_AODB, db)
        fileformat = self.formatter.FILE_EXTENSION
        ident = self.emit.getId()
        fn = f"{ident}-7-messages.{fileformat}"
        filename = os.path.join(basename, fn)
        if os.path.exists(filename) and not overwrite:
            logger.warning(f"file {filename} already exist, not saved")
            return (False, "FormatMessage::save file already exist")

        with open(filename, "w") as fp:
            for l in self.output:
                fp.write(str(l) + "\n")
        logger.debug(f"saved {fn}")

        return (True, "FormatMessage::save saved")
