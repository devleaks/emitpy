import json
import logging

from ..constants import REDIS_DATABASE, REDIS_QUEUE
from ..parameters import REDIS_CONNECT

logger = logging.getLogger("Queue")

QUEUE_NAME_SEP = ":"

class Queue:

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
        if redis.exists(REDIS_DATABASE.QUEUES.value):
            qs = redis.smembers(REDIS_DATABASE.QUEUES.value)
            for q in qs:
                qn = Queue.getQueueName(q.decode("UTF-8"))
                queues[qn] = Queue.loadFromDB(redis, qn)
            logger.debug(f":loadAllQueuesFromDB: loaded {queues.keys()}")
        else:
            logger.debug(f":loadAllQueuesFromDB: no database key")
        return queues


    @staticmethod
    def loadFromDB(redis, name):
        """
        Instantiate Queue from characteristics saved in Redis
        """
        ident = Queue.getAdminQueue(name)
        qstr = redis.get(ident)
        if qstr is not None:
            q = json.loads(qstr.decode("UTF-8"))
            logger.debug(f":create: created {name}")
            return Queue(name=name, formatter_name=q["formatter_name"], starttime=q["starttime"], speed=q["speed"], redis=redis)
        return None


    @staticmethod
    def delete(redis, name):
        ident = Queue.getAdminQueue(name)
        redis.srem(REDIS_DATABASE.QUEUES.value, ident)
        redis.delete(ident)
        redis.publish(REDIS_DATABASE.QUEUES.value, "del-queue:"+name)
        logger.debug(f":delete: deleted {name}")
        return (True, "Queue::delete: deleted")


    @staticmethod
    def getCombo(redis):
        prefix = REDIS_QUEUE.ADMIN_QUEUE_PREFIX.value + QUEUE_NAME_SEP
        keys = redis.keys(prefix + "*")
        return [(k.decode("utf-8").replace(prefix, ""), k.decode("utf-8").replace(prefix, "")) for k in sorted(keys)]


    @staticmethod
    def getAdminQueue(name):
        return REDIS_QUEUE.ADMIN_QUEUE_PREFIX.value + QUEUE_NAME_SEP + name

    @staticmethod
    def getQueueName(admin_queue_name):
        return admin_queue_name.replace(REDIS_QUEUE.ADMIN_QUEUE_PREFIX.value + QUEUE_NAME_SEP, "")


    def reset(self, speed: float = 1, starttime: str = None):
        self.speed = speed
        self.starttime = starttime
        return self.save()

    def saveDB(self):
        """
        Saves Queue characteristics in a structure for Broadcaster
        Also saves Queue existence in "list of queues" set ("Queue Database"), to build combo, etc.
        """
        ident = Queue.getAdminQueue(self.name)
        self.redis.set(ident, json.dumps({
            "name": self.name,
            "formatter_name": self.formatter_name,
            "speed": self.speed,
            "starttime": self.starttime
            }))
        self.redis.sadd(REDIS_DATABASE.QUEUES.value, ident)
        logger.debug(f"Queue {ident} saved")

        redis.publish(REDIS_DATABASE.QUEUES.value, "new-queue:"+self.name)
        logger.debug(f"Hypercaster notified for {ident}")

        return (True, "Queue::save: saved")
