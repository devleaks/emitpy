import json
import logging

from ..constants import REDIS_DATABASE, ID_SEP
from ..parameters import REDIS_CONNECT
from ..utils import make_key

logger = logging.getLogger("Queue")


class Queue:

    DATABASE = REDIS_DATABASE.QUEUES.value + ID_SEP

    def __init__(self, name: str, formatter_name: str, starttime: str = None, speed: float = 1, redis = None):
        self.name = name
        self.formatter_name = formatter_name
        self.speed = speed
        self.starttime = starttime
        self.redis = redis


    @staticmethod
    def loadAllQueuesFromDB(redis):
        """
        Instantiate Queue from characteristics saved in Redis
        """
        queues = {}
        keys = redis.keys(Queue.DATABASE + "*")
        if keys is not None and len(keys) > 0:
            for q in keys:
                qn = q.decode("UTF-8").replace(Queue.DATABASE, "")
                queues[qn] = Queue.loadFromDB(redis, qn)
            logger.debug(f":loadAllQueuesFromDB: loaded {queues.keys()}")
        logger.debug(f":loadAllQueuesFromDB: no queues")
        return queues


    @staticmethod
    def loadFromDB(redis, name):
        """
        Instantiate Queue from characteristics saved in Redis
        """
        ident = make_key(REDIS_DATABASE.QUEUES.value, name)
        qstr = redis.get(ident)
        if qstr is not None:
            q = json.loads(qstr.decode("UTF-8"))
            logger.debug(f":create: created {name}")
            return Queue(name=name, formatter_name=q["formatter_name"], starttime=q["starttime"], speed=q["speed"], redis=redis)
        return None


    @staticmethod
    def delete(redis, name):
        ident = make_key(REDIS_DATABASE.QUEUES.value, name)
        redis.srem(REDIS_DATABASE.QUEUES.value, ident)
        redis.delete(ident)
        redis.publish(REDIS_DATABASE.QUEUES.value, "del-queue:"+name)
        logger.debug(f":delete: deleted {name}")
        return (True, "Queue::delete: deleted")


    @staticmethod
    def getCombo(redis):
        keys = redis.keys(Queue.DATABASE + "*")
        return [(k.decode("utf-8").replace(Queue.DATABASE, ""), k.decode("utf-8").replace(Queue.DATABASE, "")) for k in sorted(keys)]


    def reset(self, speed: float = 1, starttime: str = None):
        self.speed = speed
        self.starttime = starttime
        return self.save()

    def saveDB(self):
        """
        Saves Queue characteristics in a structure for Broadcaster
        Also saves Queue existence in "list of queues" set ("Queue Database"), to build combo, etc.
        """
        ident = make_key(REDIS_DATABASE.QUEUES.value, self.name)
        self.redis.set(ident, json.dumps({
            "name": self.name,
            "formatter_name": self.formatter_name,
            "speed": self.speed,
            "starttime": self.starttime
            }))
        logger.debug(f"Queue {ident} saved")

        self.redis.publish(REDIS_DATABASE.QUEUES.value, "new-queue:"+self.name)
        logger.debug(f"Hypercaster notified for {ident}")

        return (True, "Queue::save: saved")
