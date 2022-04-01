import json
import logging

from redis import Redis
from ..constants import REDIS_DATABASE, REDIS_QUEUE

logger = logging.getLogger("Queue")


class Queue:

    def __init__(self, name: str, formatter_name: str, starttime: str, speed: float = 1):
        self.name = name
        self.formatter_name = formatter_name
        self.speed = speed
        self.starttime = starttime


    @staticmethod
    def create(name):
        """
        Instantiate Queue from characteristics saved in Redis
        """
        r = Redis()
        ident = Queue.getAdminQueue(name)
        qstr = r.get(ident)
        q = json.loads(qstr.decode("UTF-8"))
        logger.debug(f":create: created {name}")
        return Queue(name=name, formatter_name=q["formatter_name"], starttime=q["starttime"], speed=q["speed"])


    @staticmethod
    def delete(name):
        r = Redis()
        ident = Queue.getAdminQueue(name)
        r.srem(REDIS_DATABASE.QUEUES.value, ident)
        r.delete(ident)
        r.publish(REDIS_DATABASE.QUEUES.value, "del-queue:"+name)
        logger.debug(f":delete: deleted {name}")
        return (True, "Queue::delete: deleted")


    @staticmethod
    def getCombo():
        prefix = REDIS_QUEUE.ADMIN_QUEUE_PREFIX.value + "-"
        r = Redis()
        keys = r.keys(prefix + "*")
        return [(k.decode("utf-8").replace(prefix, ""), k.decode("utf-8").replace(prefix, "")) for k in sorted(keys)]


    @staticmethod
    def getAdminQueue(name):
        return REDIS_QUEUE.ADMIN_QUEUE_PREFIX.value + "-" + name

    @staticmethod
    def getQueueName(admin_queue_name):
        return admin_queue_name.replace(REDIS_QUEUE.ADMIN_QUEUE_PREFIX.value + "-", "")


    def save(self):
        """
        Saves Queue characteristics in a structure for Broadcaster
        Also saves Queue existence in "list of queues" set ("Queue Database"), to build combo, etc.
        """
        r = Redis()
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
