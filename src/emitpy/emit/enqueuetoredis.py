#  Python class to format features for output and enqueue for broadcast
#
import os
import logging
from datetime import datetime
import json

from .format import Format
from .queue import Queue
from emitpy.constants import REDIS_DATABASE, REDIS_TYPE, ID_SEP, QUEUE_DATA
from emitpy.utils import key_path

logger = logging.getLogger("EnqueueToRedis")


class EnqueueToRedis(Format):  # could/should inherit from Format


    def __init__(self, emit: "Emit", queue: Queue, redis = None):
        r = queue.redis if queue is not None else redis
        if r is None:
            logger.warning(f":__init__: no redis")
            return
        formatter = Format.getFormatter(queue.formatter_name)
        Format.__init__(self, emit, formatter)
        self.queue = queue
        self.redis = r


    @staticmethod
    def dequeue(redis, ident: str, queue: str):
        # Remove ident entries from sending queue.
        # 1. Remove queued elements
        oldvalues = redis.smembers(ident)
        oset = redis.pipeline()
        if oldvalues and len(oldvalues) > 0:
            oset.zrem(queue, *oldvalues)
            logger.debug(f":dequeue: deleted {len(oldvalues)} entries for {ident}")  #optimistic
        else:
            logger.debug(f":dequeue: no enqueued entries for {ident}")
        # 2. Remove enqueued list
        oset.delete(ident)
        oset.execute()
        logger.debug(f":dequeue: deleted {ident}")
        return (True, f"EnqueueToRedis::dequeue dequeued {ident}")


    @staticmethod
    def delete(redis, ident: str, queue: str = None):
        # Remove ident entries from sending queue if queue is provided.
        # Remove ident from list of emits (normally, this is done with expiration date).

        # If last character in the ID_SEP-separated domain is a REDIS_TYPE, we remove it
        a = ident.split(ID_SEP)
        if len(a[-1]) == 1 and a[-1] in [e.value for e in REDIS_TYPE]:
            ident = ID_SEP.join(a[:-1])
        if queue is not None:
            EnqueueToRedis.dequeue(redis, ident, queue)
        redis.delete(ident)
        logger.debug(f":delete: deleted {ident}")
        return (True, f"EnqueueToRedis::delete deleted {ident}")


    @staticmethod
    def pias(redis, ident: str, queue: str):
        # Play it again Sam. Re-enqueue an existing formatted set.
        # Ident must be a key name to a set of formatted, enqueued members

        # dequeue values to avoid duplicates
        oldvalues = redis.smembers(ident)
        oset = redis.pipeline()
        if oldvalues and len(oldvalues) > 0:
            oset.zrem(queue, *oldvalues)
            logger.debug(f":pias: removed {len(oldvalues)} old entries")

        # enqueue new values (the same ones)
        emit = {}
        for f1 in oldvalues:
            f2 = f1.decode("UTF-8")
            f = json.loads(f2)
            emit[f2] = f["properties"]["emit-absolute-time"]

        oset.zadd(key_path(QUEUE_DATA, queue), emit)
        logger.debug(f":pias: added {len(oldvalues)} new entries to sorted set {queue}")

        # logger.debug(f":enqueue: notifying {ADM_QUEUE_PREFIX+queue} of new data ({NEW_DATA})..")
        # oset.publish(ADM_QUEUE_PREFIX+queue, NEW_DATA)
        # logger.debug(f":enqueue: ..done")

        logger.debug(f":pias: executing..")
        oset.execute()
        logger.debug(f":pias: ..done")
        return (True, f"EnqueueToRedis::pias enqueued {ident}")


    def getKey(self, extension):
        # note: self.formatter is a class
        return key_path(self.emit.getKey(None), self.queue.name, extension)


    def save(self, overwrite: bool = False):
        """
        Save formatted emission to Redis.
        """
        if self.output is None or len(self.output) == 0:
            logger.warning(":save: no emission point")
            return (False, "EnqueueToRedis::save: no emission point")

        # note: self.formatter is a class
        formatted_id = key_path(self.emit.getKey(None), self.formatter.NAME, REDIS_TYPE.FORMAT.value)
        n = self.redis.scard(formatted_id)
        if n > 0 and not overwrite:
            logger.warning(f":save: key {formatted_id} already exist, not saved")
            return (False, "EnqueueToRedis::save key already exist")

        oset = self.redis.pipeline()
        if n > 0:
            oset.delete(formatted_id)
        tosave = []
        for f in self.output:
            tosave.append(str(f))  # str applies the formatting
        oset.sadd(formatted_id, *tosave)
        oset.execute()
        logger.debug(f":save: key {formatted_id} saved {len(tosave)} entries")
        return (True, "EnqueueToRedis::save completed")


    def enqueue(self):
        """
        Stores Sorted Set members in new variable so that we can remove them on update
        """
        if self.output is None or len(self.output) == 0:
            logger.warning(":enqueue: no emission point")
            return (False, "FormatToRedis::enqueue: no emission point")

        enq_id = self.getKey(REDIS_TYPE.QUEUE.value)
        oldvalues = self.redis.smembers(enq_id)
        oset = self.redis.pipeline()  # set
        if oldvalues and len(oldvalues) > 0:
            # dequeue old values
            oset.zrem(self.queue.getDataKey(), *oldvalues)  # #0
            oset.delete(enq_id)  # #1
            logger.debug(f":enqueue: removed old entries (count below, after execution of pipeline)")

        emit = {}
        for f in self.output:
            emit[str(f)] = f.ts
        oset.sadd(enq_id, *list(emit.keys()))  # #2

        minv = min(emit.values())
        mindt = datetime.fromtimestamp(minv).astimezone().isoformat()
        maxv = max(emit.values())
        maxdt = datetime.fromtimestamp(maxv).astimezone().isoformat()
        logger.debug(f":enqueue: saved {len(emit)} new entries to {enq_id}, from ts={minv}({mindt}) to ts={maxv} ({maxdt})")

        # enqueue new values
        oset.zadd(self.queue.getDataKey(), emit)  # #3
        logger.debug(f":enqueue: added {len(emit)} new entries to sorted set {self.queue.name}")

        # logger.debug(f":enqueue: notifying {ADM_QUEUE_PREFIX+self.queue.name} of new data ({NEW_DATA})..")
        # oset.publish(ADM_QUEUE_PREFIX+self.queue.name, NEW_DATA)  # #4
        # logger.debug(f":enqueue: ..done")

        retval = oset.execute()
        logger.debug(f":enqueue: pipeline: {retval}")
        logger.debug(f":enqueue: removed {retval[0]}/{len(oldvalues)} old entries")
        logger.debug(f":enqueue: enqueued")
        return (True, "EnqueueToRedis::enqueue completed")
