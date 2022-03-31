#  Python classes to format features for output to different channel requirements
#
import logging
from datetime import datetime

from ..geo import printFeatures
from ..constants import FEATPROP

logger = logging.getLogger("Formatter")


class Formatter:

    def __init__(self, feature: "Feature"):
        self.feature = feature
        self.ts = feature.getAbsoluteEmissionTime()

    def __str__(self):
        return json.dumps(self.feature)


class Format:

    def __init__(self, emit: "Emit", formatter: Formatter):
        self.emit = emit
        self.formatter = formatter
        self.output = []
        self.version = 0

    @staticmethod
    def getCombo():
        return [
            ("raw", "Raw"),
            ("adsb", "ADS-B"),
            ("view", "Viewer"),
            ("lt", "X-Plane LiveTraffic")
        ]

    def format(self):
        if self.emit.scheduled_emit is None or len(self.emit.scheduled_emit) == 0:
            logger.warning("Format::run: no emission point")
            return (False, "Format::run no emission point")

        self.output = []  # reset if called more than once
        br = filter(lambda f: f.getProp(FEATPROP.BROADCAST.value), self.emit.scheduled_emit)
        bq = sorted(br, key=lambda f: f.getRelativeEmissionTime())
        self.output = list(map(self.formatter, bq))
        logger.debug(f':run: formatted {len(self.output)} / {len(self.emit.scheduled_emit)}, version {self.version}')
        self.version = self.version + 1
        return (True, "Format::run completed")


    def save(self, overwrite: bool = False):
        basename = os.path.join(AODB_DIR, FLIGHT_DATABASE)
        fileformat = self.formatter.FILE_FORMAT
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
