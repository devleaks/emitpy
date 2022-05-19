#  Python classes to format features for output to different channel requirements
#
import os
import logging
import datetime

from .format import Format
from .queue import Queue
from .broadcaster import NEW_DATA, ADM_QUEUE_PREFIX
from emitpy.constants import REDIS_DATABASE, REDIS_TYPE
from emitpy.parameters import REDIS_CONNECT
from emitpy.utils import make_key

logger = logging.getLogger("EnqueueToRedis")


class EnqueueToRedis(Format):  # could/should inherit from Format


    def __init__(self, emit: "Emit", queue: Queue, redis = None):
        r = queue.redis if queue is not None else redis
        if r is None:
            return (False, f"EnqueueToRedis::__init__ no redis")
        formatter = Format.getFormatter(queue.formatter_name)
        Format.__init__(self, emit, formatter)
        self.queue = queue
        self.redis = r


    @staticmethod
    def dequeue(redis, ident: str, queue: str):
        # Remove ident entries from sending queue.
        enqueued = make_key(ident, REDIS_TYPE.QUEUE.value)
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
            EnqueueToRedis.dequeue(redis, ident, queue)
        # 2. Remove formatted
        emits = make_key(ident, REDIS_TYPE.FORMAT.value)
        redis.delete(emits)
        logger.debug(f":delete: deleted {emits} format")
        # 3. Remove messages
        emits = make_key(ident, REDIS_TYPE.EMIT_MESSAGE.value)
        redis.delete(emits)
        logger.debug(f":delete: deleted {emits} messages")
        # 4. Remove emit meta
        emits = make_key(ident, REDIS_TYPE.EMIT_META.value)
        redis.delete(emits)
        logger.debug(f":delete: deleted {emits} meta data")
        # 5. Remove emit
        emits = make_key(ident, REDIS_TYPE.EMIT.value)
        redis.delete(emits)
        logger.debug(f":delete: deleted {emits} emits")
        return (True, f"EnqueueToRedis::delete deleted {ident}")


    def save(self, overwrite: bool = False):
        """
        Save flight paths to file for emitted positions.
        """
        if self.output is None or len(self.output) == 0:
            logger.warning(":save: no emission point")
            return (False, "EnqueueToRedis::save: no emission point")

        emit_id = self.emit.getKey(REDIS_TYPE.FORMAT.value)  # ident + REDIS_TYPE.EMIT.value

        n = self.redis.scard(emit_id)
        if n > 0 and not overwrite:
            logger.warning(f":save: key {emit_id} already exist, not saved")
            return (False, "EnqueueToRedis::save key already exist")

        if n > 0:
            self.redis.delete(emit_id)
        tosave = []
        for f in self.output:
            tosave.append(str(f))
        self.redis.sadd(emit_id, *tosave)
        logger.debug(f":save: key {emit_id} saved {len(tosave)} entries")
        return (True, "EnqueueToRedis::save completed")


    def enqueue(self):
        """
        Stores Sorted Set members in new variable so that we can remove them on update
        """
        if self.output is None or len(self.output) == 0:
            logger.warning(":enqueue: no emission point")
            return (False, "FormatToRedis::enqueue: no emission point")

        emit_id = self.emit.getKey(REDIS_TYPE.QUEUE.value)
        oldvalues = self.redis.smembers(emit_id)
        if oldvalues and len(oldvalues) > 0:
            self.redis.zrem(self.queue.name, *oldvalues)
            self.redis.delete(emit_id)
            logger.debug(f":enqueue: removed {len(oldvalues)} old entries")

        emit = {}
        for f in self.output:
            emit[str(f)] = f.ts
        self.redis.zadd(self.queue.name, emit)
        self.redis.sadd(emit_id, *list(emit.keys()))
        logger.debug(f":enqueue: added {len(emit)} new entries")

        logger.debug(f":enqueue: notifying {ADM_QUEUE_PREFIX+self.queue.name} of new data ({NEW_DATA})")
        self.redis.publish(ADM_QUEUE_PREFIX+self.queue.name, NEW_DATA)

        return (True, "EnqueueToRedis::enqueue completed")
