"""
Keep simple statistics about the use of the application.
"""
import redis
from enum import Enum

STATS_PREFIX = "stats$"

class STATS(Enum):
    FLIGHTS = "flights"
    SERVICES = "services"
    ENQUEUES = "enqueues"
    DEQUEUES = "dequeues"
    SENT = "sent"



class Stat:

    def __init__(self):
        self.redis = redis.Redis()

    def add(name: str, incr: int = 1):
        self.redis.incrby(STATS_PREFIX+name, incr)
        return self.redis.get(STATS_PREFIX+name)

    def getLength(name: str):
        return self.redis.scard(name)

    def getLengthZ(name: str):
        return self.redis.zcard(name)