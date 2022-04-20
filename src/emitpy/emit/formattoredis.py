#  Python classes to format features for output to different channel requirements
#
import os
import logging
import datetime
import redis

from .format import Format, Formatter
from ..constants import REDIS_QUEUE, REDIS_DATABASE, REDIS_TYPE
from ..parameters import REDIS_CONNECT

logger = logging.getLogger("FormatToRedis")


class FormatToRedis(Format):

    def __init__(self, emit: "Emit", formatter: Formatter):
        Format.__init__(self, emit=emit, formatter=formatter)
        self.redis = redis.Redis(**REDIS_CONNECT)


    @staticmethod
    def list():
        keys = self.redis.keys("*"+REDIS_TYPE.QUEUE.value)
        return [(k, k) for k in sorted(keys)]


    @staticmethod
    def dequeue(ident: str, queue: str):
        r = redis.Redis(**REDIS_CONNECT)
        # Remove ident entries from sending queue.
        enqueued = ident + REDIS_TYPE.QUEUE.value
        # 1. Remove queued elements
        oldvalues = r.smembers(enqueued)
        if oldvalues and len(oldvalues) > 0:
            r.zrem(queue, *oldvalues)
            # 2. Remove enqueued list
            r.delete(enqueued)
            logger.debug(f":dequeue: dequeued {len(oldvalues)} entries for {ident}")
        else:
            logger.debug(f":dequeue: no enqueued entries for {len(oldvalues)}")
        return (True, f"FormatToRedis::dequeue dequeued {ident}")


    @staticmethod
    def delete(ident: str, queue: str = None):
        # Remove ident entries from sending queue if queue is provided.
        # Remove ident from list of emits (normally, this is done with expiration date).
        r = redis.Redis(**REDIS_CONNECT)
        enqueued = ident + REDIS_TYPE.QUEUE.value
        # 1. Dequeue
        if queue is not None:
            FormatToRedis.dequeue(ident, queue)
        # 2. Remove emit
        r.delete(enqueued)
        # 3. Remove from list of available emissions
        r.srem(REDIS_DATABASE.MOVEMENTS.value, ident)
        logger.debug(f":delete: deleted {ident} emits")
        return (True, f"FormatToRedis::delete deleted {ident}")


    def save(self, overwrite: bool = False):
        """
        Save flight paths to file for emitted positions.
        """
        if self.output is None or len(self.output) == 0:
            logger.warning(":save: no emission point")
            return (False, "FormatToRedis::save: no emission point")

        emit_id = self.emit.mkDBKey(REDIS_TYPE.FORMAT.value)  # ident + REDIS_TYPE.EMIT.value

        n = self.redis.scard(emit_id)
        if n > 0 and not overwrite:
            logger.warning(f":save: key {emit_id} already exist, not saved")
            return (False, "FormatToRedis::save key already exist")

        if n > 0:
            self.redis.delete(emit_id)
        tosave = []
        for f in self.output:
            tosave.append(str(f))
        self.redis.sadd(emit_id, *tosave)
        logger.debug(f":save: key {emit_id} saved {len(tosave)} entries")
        return (True, "FormatToRedis::save completed")


    def enqueue(self, queue: str):
        """
        Stores Sorted Set members in new variable so that we can remove them on update
        """
        if self.output is None or len(self.output) == 0:
            logger.warning(":enqueue: no emission point")
            return (False, "FormatToRedis::enqueue: no emission point")

        ident = self.emit.getId()
        emit_id = self.emit.mkDBKey(REDIS_TYPE.QUEUE.value)

        oldvalues = self.redis.smembers(emit_id)
        if oldvalues and len(oldvalues) > 0:
            self.redis.zrem(queue, *oldvalues)
            self.redis.delete(emit_id)
            logger.debug(f":enqueue: removed {len(oldvalues)} old entries")

        emit = {}
        for f in self.output:
            emit[str(f)] = f.ts
        self.redis.zadd(queue, emit)
        self.redis.sadd(emit_id, *list(emit.keys()))
        logger.debug(f":enqueue: added {len(emit)} new entries")
        self.redis.publish("Q"+queue, "new-data")

        return (True, "FormatToRedis::enqueue completed")

