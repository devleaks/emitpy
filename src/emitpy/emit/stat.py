"""
Keep simple statistics about the use of the application.
"""
import redis
from datetime import datetime
from enum import Enum

from ..parameters import REDIS_CONNECT

STATS_PREFIX = "stats$"

class STATS(Enum):
    FLIGHTS = "flights"
    SERVICES = "services"
    ENQUEUES = "enqueues"
    DEQUEUES = "dequeues"
    SENT = "sent"
    SNAPSHOT = "snap"



class Stat:

    def __init__(self):
        self.redis = redis.Redis(**REDIS_CONNECT)
        self.stats = []

    def init(self):
        """
        Initializes the Stat object. Reads existing queues, build stats for each queue.
        """
        pass

    def add(name: str, incr: int = 1, param:str = None):
        k = STATS_PREFIX + name + (":" + param if param is not None else "")
        self.stats.append(k) if k not in self.stats else ""
        self.redis.incrby(k, incr)
        return self.redis.get(k)

    def getLength(name: str):
        return self.redis.scard(name)

    def getLengthZ(name: str):
        return self.redis.zcard(name)

    def snapshot(self):
        statk = STATS.SNAPSHOT.value + ":" + datetime.now().isoformat()
        stats = {}
        for k in self.stats:
            stats[k] = self.redis.get(k)
        self.redis.set(statk, stats)
        return (True, "Snapshop completed")