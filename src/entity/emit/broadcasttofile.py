#  Python classes to format features for output to different channel requirements
#
import os
import logging
import datetime

from ..constants import FLIGHT_DATABASE, FEATPROP
from ..parameters import AODB_DIR

from .broadcast import Broadcast, Formatter

logger = logging.getLogger("BroadcastToFile")


class BroadcastToFile(Broadcast):

    def __init__(self, emit: "Emit", starttime: datetime, formatter: Formatter):
        Broadcast.__init__(self, emit=emit, starttime=starttime, formatter=formatter)
        self.emit = emit
        self.starttime = starttime
        self.formatter = formatter

        self.broadcast = []


    def run(self):
        """
        Save flight paths to file for emitted positions.
        """
        super().run()

        basename = os.path.join(AODB_DIR, FLIGHT_DATABASE)
        fileformat = self.formatter.FILE_FORMAT
        ident = self.emit.getId()
        fn = f"{ident}-6-broadcast.{fileformat}"
        filename = os.path.join(basename, fn)
        with open(filename, "w") as fp:
            for l in self.broadcast:
                fp.write(str(l)+"\n")

        logger.debug(f":save: saved {fn}")
