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

    def __str__(self):
        return json.dumps(self.feature)


class Broadcast:

    def __init__(self, emit: "Emit", starttime: datetime, formatter: Formatter):
        self.emit = emit
        self.starttime = starttime
        self.broadcast = []
        self.version = 0


    def run(self):
        self.broadcast = []  # reset if called more than once
        bq = sorted(self.emit.broadcast, key=lambda f: f.getBroadcastTime())
        startts = self.starttime.timestamp()
        logger.debug(f':run: start time {self.starttime} ({startts})')

        # skipping events before start of emission
        curr = 0
        while bq[curr].getBroadcastTime() < startts and curr < len(bq) - 1:
            # logger.debug(f':run: skipping {curr} {bq[curr].getBroadcastTime()}')
            # @todo: add option to "force send" late events if necessary?
            curr = curr + 1

        logger.debug(f':run: skipped {curr} / {len(bq)}')

        sent = 0
        for idx in range(curr, len(bq)):
            e = bq[idx]
            if e.getProp(FEATPROP.BROADCAST.value):
                f = self.formatter(e)
                self.broadcast.append(f)
                logger.debug(f':run: broadcasting at {e.getProp(FEATPROP.BROADCAST_ABS_TIME.value)}')
                sent = sent + 1

        logger.debug(f':run: broadcasted {sent} / {len(bq)}')
        self.version = self.version + 1

    def get(self):
        return printFeatures(self.broadcast, "broadcast", True)
