#  Python classes to format features for output to different channel requirements
#
import os
import logging
import datetime
import redis

from .format import Format
from .formattoredis import FormatToRedis
from .queue import Queue
from ..constants import REDIS_QUEUE, REDIS_DATABASE, REDIS_TYPE
from ..parameters import REDIS_CONNECT

logger = logging.getLogger("EnqueueToRedis")


class EnqueueToRedis(FormatToRedis):  # could/should inherit from Format


    def __init__(self, emit: "Emit", queue: Queue):
        formatter = Format.getFormatter(queue.formatter_name)
        FormatToRedis.__init__(self, emit, formatter)
        self.queue = queue


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
            logger.debug(f":enqueue: deleted {len(oldvalues)} entries")
        else:
            logger.debug(f":enqueue: no enqueued entries for {len(oldvalues)}")
        return (True, f"Format::dequeue dequeued {ident}")


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
        logger.debug(f":enqueue: deleted {ident} emits")
        return (True, f"Format::delete deleted {ident}")


    def enqueue(self):
        """
        Stores Sorted Set members in new variable so that we can remove them on update
        """
        if self.output is None or len(self.output) == 0:
            logger.warning(":enqueue: no emission point")
            return (False, "Enqueue::enqueue: no emission point")

        ident = self.emit.getId()
        ident = ident + REDIS_TYPE.QUEUE.value

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

