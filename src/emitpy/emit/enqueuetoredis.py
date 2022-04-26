#  Python classes to format features for output to different channel requirements
#
import os
import logging
import datetime

from .format import Format
from .formattoredis import FormatToRedis
from .queue import Queue
from ..constants import REDIS_QUEUE, REDIS_DATABASE, REDIS_TYPE
from ..parameters import REDIS_CONNECT

logger = logging.getLogger("EnqueueToRedis")


class EnqueueToRedis(FormatToRedis):  # could/should inherit from Format


    def __init__(self, emit: "Emit", queue: Queue, redis = None):
        r = queue.redis if queue is not None else redis
        formatter = Format.getFormatter(queue.formatter_name)
        FormatToRedis.__init__(self, emit, formatter, r)
        self.queue = queue
        self.redis = r


    @staticmethod
    def dequeue(redis, ident: str, queue: str):
        # Remove ident entries from sending queue.
        enqueued = ident + REDIS_TYPE.QUEUE.value
        # 1. Remove queued elements
        oldvalues = redis.smembers(enqueued)
        if oldvalues and len(oldvalues) > 0:
            redis.zrem(queue, *oldvalues)
            logger.debug(f":dequeue: deleted {len(oldvalues)} entries for {enqueued}")
        else:
            logger.debug(f":dequeue: no enqueued entries for {enqueued}")
        # 2. Remove enqueued list
        redis.delete(enqueued)
        logger.debug(f":dequeue: deleted {enqueued}")

        return (True, f"EnqueueToRedis::dequeue dequeued {ident}")


    @staticmethod
    def delete(redis, ident: str, queue: str = None):
        # Remove ident entries from sending queue if queue is provided.
        # Remove ident from list of emits (normally, this is done with expiration date).
        # 1. Dequeue
        if queue is not None:
            FormatToRedis.dequeue(ident, queue)
        # 2. Remove formatted
        emits = ident + REDIS_TYPE.FORMAT.value
        redis.delete(emits)
        logger.debug(f":delete: deleted {emits} formats")
        # 3. Remove emit
        emits = ident + REDIS_TYPE.EMIT.value
        redis.delete(emits)
        logger.debug(f":delete: deleted {emits} emits")
        # 4. Remove emit meta
        emits = ident + REDIS_TYPE.EMIT_META.value
        redis.delete(emits)
        logger.debug(f":delete: deleted {emits} emit meta data")
        # 5. Remove from list of available emissions
        redis.srem(REDIS_DATABASE.MOVEMENTS.value, ident)
        logger.debug(f":delete: deleted {ident} emit")
        return (True, f"EnqueueToRedis::delete deleted {ident}")


    def enqueue(self):
        """
        Stores Sorted Set members in new variable so that we can remove them on update
        """
        if self.output is None or len(self.output) == 0:
            logger.warning(":enqueue: no emission point")
            return (False, "EnqueueToRedis::enqueue: no emission point")

        ident = self.emit.mkDBKey(REDIS_TYPE.QUEUE.value)
        oldvalues = self.redis.smembers(ident)
        if oldvalues and len(oldvalues) > 0:
            self.redis.zrem(self.queue.name, *oldvalues)
            self.redis.delete(ident)
            logger.debug(f":enqueue: removed {len(oldvalues)} old entries")

        emit = {}
        for f in self.output:
            emit[str(f)] = f.ts
        self.redis.zadd(self.queue.name, emit)
        self.redis.sadd(ident, *list(emit.keys()))
        logger.debug(f":enqueue: added {len(emit)} new entries")
        self.redis.publish("Q"+self.queue.name, "new-data")

        return (True, "EnqueueToRedis::enqueue completed")

