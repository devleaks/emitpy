import json
import logging
from datetime import datetime

from emitpy.constants import INTERNAL_QUEUES, REDIS_DATABASE, ID_SEP, LIVETRAFFIC_QUEUE, QUEUE_DATA
from emitpy.utils import key_path

logger = logging.getLogger("Queue")

QUIT = "quit"
RUN  = "run"
STOP = "stop"
RESET = "reset"
CONTINUE = "continue"


class Queue:

    def __init__(self, name: str, formatter_name: str, starttime: str = None, speed: float = 1, start: bool=True, redis = None):
        self.name = name
        self.formatter_name = formatter_name
        self.speed = speed
        self.starttime = starttime
        self.status = RUN if start else STOP
        self.mode = RESET
        self.redis = redis


    @staticmethod
    def getAllQueues(redis):
        keys = redis.keys(key_path(REDIS_DATABASE.QUEUES.value, "*"))
        if keys is not None:
            return list(filter(lambda x: not x.startswith(QUEUE_DATA), [k.decode("UTF-8") for k in keys]))
        return None


    @staticmethod
    def loadAllQueuesFromDB(redis):
        """
        Instantiate Queue from characteristics saved in Redis
        """
        queues = {}
        keys = Queue.getAllQueues(redis)
        if keys is not None and len(keys) > 0:
            for q in keys:
                qa = q.split(ID_SEP)
                qn = qa[-1]
                if qn != QUIT:
                    queues[qn] = Queue.loadFromDB(redis, qn)
                else:
                    logger.warning(f":loadAllQueuesFromDB: cannot create queue named '{QUIT}' (reserved queue name)")
            logger.debug(f":loadAllQueuesFromDB: loaded {queues.keys()}")
        else:
            logger.debug(f":loadAllQueuesFromDB: no queues")
        return queues


    @staticmethod
    def loadFromDB(redis, name):
        """
        Instantiate Queue from characteristics saved in Redis
        """
        ident = Queue.mkKey(name)
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
        if name in INTERNAL_QUEUES.keys() or name == LIVETRAFFIC_QUEUE:
            return (False, "Queue::delete: cannot delete default queue")
        # 1. Remove definition
        ident = Queue.mkKey(name)
        redis.delete(ident)
        # 2. Remove preparation queue
        data = Queue.mkDataKey(name)
        redis.delete(data)
        logger.debug(f":delete: deleted {name}")
        return (True, "Queue::delete: deleted")


    @staticmethod
    def getCombo(redis):
        redis.select(0)
        keys = Queue.getAllQueues(redis)
        qns = [k.split(ID_SEP)[-1] for k in keys]
        return [(k, k) for k in sorted(qns)]


    @staticmethod
    def mkKey(name):
        return key_path(REDIS_DATABASE.QUEUES.value, name)


    @staticmethod
    def mkDataKey(name):
        return key_path(QUEUE_DATA, name)


    def getKey(self):
        return Queue.mkKey(self.name)


    def getDataKey(self):
        return Queue.mkDataKey(self.name)


    def reset(self, speed: float = 1, starttime: str = None, start: bool = True):
        self.speed = speed
        self.starttime = starttime
        self.status = RUN if start else STOP
        return self.save()


    def save(self, currtime: datetime = None):
        """
        Saves Queue characteristics in a structure for Broadcaster
        Also saves Queue existence in "list of queues" set ("Queue Database"), to build combo, etc.
        """
        ident = self.getKey()
        self.redis.set(ident, json.dumps({
            "name": self.name,
            "formatter_name": self.formatter_name,
            "speed": self.speed,
            "starttime": self.starttime,
            "currenttime": currtime,
            "mode": self.mode,
            "status": self.status
        }))
        logger.debug(f":save: {ident} saved")
        return (True, "Queue::save: saved")
