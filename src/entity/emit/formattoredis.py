#  Python classes to format features for output to different channel requirements
#
import os
import logging
import datetime
import redis

from .format import Format, Formatter
from ..constants import REDIS_QUEUE

logger = logging.getLogger("FormatToRedis")


class FormatToRedis(Format):

    def __init__(self, emit: "Emit", formatter: Formatter):
        Format.__init__(self, emit=emit, formatter=formatter)
        self.redis = redis.Redis()


    def save(self, overwrite: bool = False):
        """
        Save flight paths to file for emitted positions.
        """
        ident = self.emit.getId()
        ident = ident + "-out"

        n = self.redis.scard(ident)
        if n > 0 and not overwrite:
            logger.warning(f":save: key {ident} already exist, not saved")
            return (False, "FormatToRedis::save key already exist")

        if n > 0:
            self.redis.delete(ident)
        tosave = []
        for f in self.output:
            tosave.append(str(f))
        self.redis.sadd(ident, *tosave)
        logger.debug(f":save: key {ident} saved {len(tosave)} entries")
        return (True, "FormatToRedis::save completed")


    def enqueue(self, name: str):
        """
        Stores Sorted Set members in new variable so that we can remove them on update
        """
        ident = self.emit.getId()
        ident = ident + "-enqueued"

        oldvalues = self.redis.smembers(ident)
        if oldvalues and len(oldvalues) > 0:
            self.redis.zrem(name, *oldvalues)
            self.redis.delete(ident)
            logger.debug(f":enqueue: removed {len(oldvalues)} old entries")

        emit = {}
        for f in self.output:
            emit[str(f)] = f.ts
        self.redis.zadd(name, emit)
        self.redis.sadd(ident, *list(emit.keys()))
        logger.debug(f":enqueue: added {len(emit)} new entries")
        self.redis.publish("Q"+name, "new-data")

        return (True, "FormatToRedis::enqueue completed")

