import json
import logging

from redis import Redis
from .format import Formatter
from ..constants import REDIS_DATABASE, REDIS_QUEUE

logger = logging.getLogger("Queue")


class Queue:

    def __init__(self, name: str, formatter: str, starttime: str, speed: float = 1):
        self.name = name
        self.formatter = formatter
        self.speed = speed

    def getAdminQueue(self):
        return REDIS_QUEUE.ADMIN_QUEUE_PREFIX.value + "-" + self.name

    def save(self):
        r = Redis()
        ident = self.getAdminQueue()
        r.set(ident, json.dumps({
            "name": self.name,
            "format": self.formatter,
            "speed": self.speed
            }))
        r.sadd(REDIS_DATABASE.QUEUES.value, ident)
        return (True, "Queue::save: saved")