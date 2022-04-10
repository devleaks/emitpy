import redis
import json
import logging

logger = logging.getLogger("Utils/Redis")

from ..constants import REDIS_DATABASE, REDIS_QUEUE, REDIS_TYPE

class RedisUtils:

    def __init__(self):
        self.redis = redis.Redis()

    def list_emits(self):
        return self.getKeys(REDIS_TYPE.EMIT.value)

    def list_queues(self):
        return ("none", "none")

    def dashboard(self):
        pass

    def inc(self, name:str, val: int = 1):
        pass

    def getKeys(self, suffix):
        keys = self.redis.keys("*"+suffix)
        return [(k.decode("utf-8").replace(suffix, ""), k.decode("utf-8").replace(suffix, "")) for k in sorted(keys)]


    def getMovementCombo(self):
        ret = self.redis.smembers(REDIS_DATABASE.MOVEMENTS.value)
        return [(f.decode("UTF-8"),f.decode("UTF-8")) for f in ret]

    def getSyncsForEmit(self, emit_id: str):
        def toEmitPoint(s: str):
            f = json.loads(s.decode('UTF-8'))
            return f  # EmitPoint(geometry=f["geometry"], properties=f["properties"])

        ident = emit_id + REDIS_TYPE.EMIT.value
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
