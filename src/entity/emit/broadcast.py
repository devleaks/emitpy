#  Python classes to format features for output to different channel requirements
#
import logging
import datetime

from .formatter import LiveTraffic
from ..constants import FEATPROP

logger = logging.getLogger("Broadcast")


class Broadcast:

    def __init__(self, emit: "Emit", starttime: datetime):
        self.emit = emit
        self.starttime = starttime


    def run(self):
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

        for idx in range(curr, len(bq)):
            e = bq[idx]
            f = LiveTraffic(e)
            logger.debug(f':run: broadcasting at {e.getProp(FEATPROP.BROADCAST_REL_TIME.value)}: {0}')
