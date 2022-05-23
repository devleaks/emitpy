import json
import logging

from emitpy.constants import REDIS_DATABASE, ID_SEP
from emitpy.utils import make_key
from emitpy.parameters import DEFAULT_QUEUES

logger = logging.getLogger("Queue")


RUN  = "run"
STOP = "stop"
NEW_QUEUE = "new-queue"
DELETE_QUEUE = "del-queue"

class Queue:

    DATABASE = REDIS_DATABASE.QUEUES.value + ID_SEP

    def __init__(self, name: str, formatter_name: str, starttime: str = None, speed: float = 1, start: bool=True, redis = None):
        self.name = name
        self.formatter_name = formatter_name
        self.speed = speed
        self.starttime = starttime
        self.status = RUN if start else STOP
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
        else:
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
            logger.debug(f":loadFromDB: loaded {name}")
            start = True
            if "status" in q and q["status"] == STOP:
                start = False
            return Queue(name=name, formatter_name=q["formatter_name"], starttime=q["starttime"], speed=q["speed"], start=start, redis=redis)
        return None


    @staticmethod
    def delete(redis, name):
        if name in DELETE_QUEUE.keys():
            return (False, "Queue::delete: cannot delete default queue")
        ident = make_key(REDIS_DATABASE.QUEUES.value, name)
        redis.srem(REDIS_DATABASE.QUEUES.value, ident)
        redis.delete(ident)
        logger.debug(f":delete: deleted {name}")
        redis.publish(REDIS_DATABASE.QUEUES.value, DELETE_QUEUE+ID_SEP+name)
        logger.debug(f"Hypercaster notified for deletion of {ident}")
        return (True, "Queue::delete: deleted")


    @staticmethod
    def getCombo(redis):
        keys = redis.keys(Queue.DATABASE + "*")
        return [(k.decode("utf-8").replace(Queue.DATABASE, ""), k.decode("utf-8").replace(Queue.DATABASE, "")) for k in sorted(keys)]


    def reset(self, speed: float = 1, starttime: str = None, start: bool = True):
        self.speed = speed
        self.starttime = starttime
        self.status = RUN if start else STOP
        return self.save()

    def save(self):
        """
        Saves Queue characteristics in a structure for Broadcaster
        Also saves Queue existence in "list of queues" set ("Queue Database"), to build combo, etc.
        """
        ident = make_key(REDIS_DATABASE.QUEUES.value, self.name)
        self.redis.set(ident, json.dumps({
            "name": self.name,
            "formatter_name": self.formatter_name,
            "speed": self.speed,
            "starttime": self.starttime,
            "status": self.status
            }))
        self.redis.sadd(REDIS_DATABASE.QUEUES.value, ident)
        logger.debug(f":save: {ident} saved")

        self.redis.publish(REDIS_DATABASE.QUEUES.value, NEW_QUEUE+ID_SEP+self.name)
        logger.debug(f"Hypercaster notified for creation of {ident}")

        return (True, "Queue::save: saved")
