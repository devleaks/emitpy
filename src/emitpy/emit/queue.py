import json
import logging

from redis import Redis
from ..constants import REDIS_DATABASE, REDIS_QUEUE
from ..parameters import REDIS_CONNECT

logger = logging.getLogger("Queue")

QUEUE_NAME_SEP = ":"

class Queue:

    def __init__(self, name: str, formatter_name: str, starttime: str = None, speed: float = 1):
        self.name = name
        self.formatter_name = formatter_name
        self.speed = speed
        self.starttime = starttime


    @staticmethod
    def loadAllQueuesFromDB():
        """
        Instantiate Queue from characteristics saved in Redis
        """
        queues = {}
        r = Redis(**REDIS_CONNECT)
        if r.exists(REDIS_DATABASE.QUEUES.value):
            qs = r.smembers(REDIS_DATABASE.QUEUES.value)
            for q in qs:
                qn = Queue.getQueueName(q.decode("UTF-8"))
                queues[qn] = Queue.loadFromDB(qn)
            logger.debug(f":loadAllQueuesFromDB: loaded {queues.keys()}")
        else:
            logger.debug(f":loadAllQueuesFromDB: no database key")
        return queues


    @staticmethod
    def loadFromDB(name):
        """
        Instantiate Queue from characteristics saved in Redis
        """
        r = Redis(**REDIS_CONNECT)
        ident = Queue.getAdminQueue(name)
        qstr = r.get(ident)
        if qstr is not None:
            q = json.loads(qstr.decode("UTF-8"))
            logger.debug(f":create: created {name}")
            return Queue(name=name, formatter_name=q["formatter_name"], starttime=q["starttime"], speed=q["speed"])
        return None


    @staticmethod
    def delete(name):
        r = Redis(**REDIS_CONNECT)
        ident = Queue.getAdminQueue(name)
        r.srem(REDIS_DATABASE.QUEUES.value, ident)
        r.delete(ident)
        r.publish(REDIS_DATABASE.QUEUES.value, "del-queue:"+name)
        logger.debug(f":delete: deleted {name}")
        return (True, "Queue::delete: deleted")


    @staticmethod
    def getCombo():
        prefix = REDIS_QUEUE.ADMIN_QUEUE_PREFIX.value + QUEUE_NAME_SEP
        r = Redis(**REDIS_CONNECT)
        keys = r.keys(prefix + "*")
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

    def save(self):
        """
        Saves Queue characteristics in a structure for Broadcaster
        Also saves Queue existence in "list of queues" set ("Queue Database"), to build combo, etc.
        """
        r = Redis(**REDIS_CONNECT)
        ident = Queue.getAdminQueue(self.name)
        r.set(ident, json.dumps({
            "name": self.name,
            "formatter_name": self.formatter_name,
            "speed": self.speed,
            "starttime": self.starttime
            }))
        r.sadd(REDIS_DATABASE.QUEUES.value, ident)
        logger.debug(f"Queue {ident} saved")

        r.publish(REDIS_DATABASE.QUEUES.value, "new-queue:"+self.name)
        logger.debug(f"Hypercaster notified for {ident}")

        return (True, "Queue::save: saved")
