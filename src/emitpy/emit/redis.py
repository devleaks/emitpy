import redis
import json
import logging
from enum import Enum

logger = logging.getLogger("RedisUtils")

from emitpy.constants import REDIS_DATABASE, REDIS_QUEUE, REDIS_TYPE, ID_SEP
from emitpy.parameters import REDIS_CONNECT
from emitpy.utils import make_key


STATS_PREFIX = "stats$"

class STATS(Enum):
    FLIGHTS = "flights"
    SERVICES = "services"
    ENQUEUES = "enqueues"
    DEQUEUES = "dequeues"
    SENT = "sent"
    PREFIX = "STATS"
    SNAPSHOT = "snap"


class RedisUtils:

    def __init__(self):
        self.redis = redis.Redis(**REDIS_CONNECT)
        self.stats = []

    def getKeys(self, suffix):
        keys = self.redis.keys("*"+suffix)
        return [(k.decode("utf-8").replace(suffix, ""), k.decode("utf-8").replace(suffix, "")) for k in sorted(keys)]

    def getQueueCombo():
        keys = self.redis.keys(REDIS_DATABASE.QUEUES.value + ID_SEP + "*")
        return [(k.decode("utf-8").replace(Queue.DATABASE, ""), k.decode("utf-8").replace(Queue.DATABASE, "")) for k in sorted(keys)]

    def list_emits(self):
        return self.getKeys(ID_SEP + REDIS_TYPE.EMIT.value)

    def getMovementCombo(self):
        ret = [f.replace(ID_SEP + REDIS_TYPE.EMIT.value, "") for f in self.getKeys(ID_SEP + REDIS_TYPE.EMIT.value)]
        return [(f.decode("UTF-8"),f.decode("UTF-8")) for f in ret]

    def getSyncsForEmit(self, emit_id: str):
        def toEmitPoint(s: str):
            f = json.loads(s.decode('UTF-8'))
            return f  # EmitPoint.new(f)

        ident = make_key(emit_id, REDIS_TYPE.EMIT.value)
        logger.debug(f":loadDB: trying to read {ident}..")
        ret = self.redis.zrange(ident, 0, -1)
        logger.debug(f":loadDB: ..got {len(ret)} members")
        emit = [toEmitPoint(f) for f in ret]
        logger.debug(f":loadDB: collected {len(emit)} points")
        s = {}
        for e in emit:
            if "properties" in e and "_mark" in e["properties"]:
                s[e["properties"]["_mark"]] = True
        return [(m, m.upper()) for m in s.keys()]

    def dashboard(self):
        pass

    def inc(self, name:str, incr: int = 1):
        self.redis.incrby(STATS.PREFIX.valuename, incr)
        if name not in self.stats:
            self.stats.append(name)

    def snapshot(self):
        statk = STATS.SNAPSHOT.value + ":" + datetime.now().isoformat()
        stats = {}
        for k in self.stats:
            stats[k] = self.redis.get(STATS.PREFIX.valuename + k)
        self.redis.set(statk, stats)
        return (True, "Snapshop completed")