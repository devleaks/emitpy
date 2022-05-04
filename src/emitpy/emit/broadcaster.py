from datetime import datetime, timedelta
import threading
import signal
import time
import redis
import logging

from emitpy.constants import REDIS_DATABASE
from emitpy.parameters import REDIS_CONNECT
from .queue import Queue

logger = logging.getLogger("Broadcaster")


# Utility functions for debugging time
def df(ts):
    return f"{datetime.fromtimestamp(ts).isoformat(timespec='seconds')} ({round(ts, 1)})"

def td(ts):
    return f"{timedelta(seconds=round(ts))} ({round(ts, 1)})"

ZPOPMIN_TIMEOUT = 10  # secs


# ##############################@@
# B R O A D C A S T E R
#
class Broadcaster:

    def __init__(self, name: str, speed: float = 1, starttime: datetime = None):
        self.name = name
        self.speed = speed
        if starttime is None:
            self._starttime = datetime.now()
        elif type(starttime) == str:
            self._starttime = datetime.fromisoformat(starttime)
        else:
            self._starttime = starttime
        # logger.debug(f":__init__: {self.name}: start_time: {self._starttime}, speed: {self.speed}")
        self.timeshift = None
        self.redis = redis.Redis(**REDIS_CONNECT)
        self.pubsub = self.redis.pubsub()
        self.setTimeshift()

    def setTimeshift(self):
        self.timeshift = datetime.now() - self.starttime()  # timedelta
        if self.timeshift < timedelta(seconds=10):
            self.timeshift = timedelta(seconds=0)
        logger.debug(f":setTimeshift: {self.name}: timeshift: {self.timeshift}, now: {df(datetime.now().timestamp())}, queue time: {df(self.now())}")
        return self.timeshift

    def starttime(self):
        if self._starttime is None:
            return datetime.now()  # should never happen...
        return self._starttime

    def reset(self, speed: float = 1, starttime: datetime = None):
        self.speed = speed
        if starttime is not None:
            if type(starttime) == str:
                self._starttime = datetime.fromisoformat(starttime)
            else:
                self._starttime = starttime
            self.setTimeshift()

    def now(self, format_output: bool = False):
        realnow = datetime.now()
        if self.speed == 1 and self.timeshift.total_seconds() == 0:
            newnow = realnow
            logger.debug(f":now: {self.name}: no time speed, no time shift: new now: {df(newnow.timestamp())}")
            return newnow.timestamp()

        logger.debug(f":now: {self.name}: asked at {df(realnow.timestamp())})")
        elapsed = realnow - (self.starttime() + self.timeshift)  # time elapsed since setTimeshift().
        logger.debug(f":now: {self.name}: real elapsed since start of queue: {elapsed})")
        if self.speed == 1:
            newnow = self.starttime() + elapsed
            logger.debug(f":now: {self.name}: no time speed: new now: {df(newnow.timestamp())}")
        else:
            newdeltasec = elapsed.total_seconds() * self.speed
            newdelta = timedelta(seconds=newdeltasec)
            newnow = self.starttime() + newdelta
            logger.debug(f":now: {self.name}: time speed {self.speed}: new elapsed: {newdelta}, new now={df(newnow.timestamp())}")
        return newnow.timestamp() if not format_output else datetime.fromtimestamp(newnow).isoformat(timespec='seconds')

    def _do_trim(self):
        now = self.now()
        logger.debug(f":_do_trim: {self.name}: {df(now)}): trimming..")
        oldones = self.redis.zrangebyscore(self.name, min=0, max=now)
        if oldones and len(oldones) > 0:
            self.redis.zrem(self.name, *oldones)
            logger.debug(f":_do_trim: {self.name}: ..removed {len(oldones)} messages..done")
        else:
            logger.debug(f":_do_trim: {self.name}: nothing to remove ..done")

    def trim(self):
        self.pubsub.subscribe("Q"+self.name)
        logger.debug(f":trim: {self.name}: listening..")
        for message in self.pubsub.listen():
            msg = message["data"]
            if type(msg) == bytes:
                msg = msg.decode('UTF-8')
            logger.debug(f":trim: {self.name}: received {msg}")
            if msg == "new-data":
                logger.debug(f":trim: {self.name}: ask sender to stop..")
                # ask run() to stop sending:
                self.oktotrim = threading.Event()
                self.rdv.set()
                logger.debug(f":trim: {self.name}: wait sender has stopped..")
                self.oktotrim.wait()
                self._do_trim()
                logger.debug(f":trim: {self.name}: tell sender to restart, provide new blocking event..")
                self.trimmingcompleted.set()
                self.rdv = threading.Event()
                logger.debug(f":trim: {self.name}: listening again..")
            elif msg == "quit":
                logger.debug(f":trim: {self.name}: quitting..")
                return
            else:
                logger.debug(f":trim: {self.name}: ignoring '{msg}'")

    def broadcast(self):
        # Blocking version of "Sender"
        logger.debug(f":run: {self.name}: pre-start trimming..")
        self._do_trim()
        logger.debug(f":run: {self.name}: ..done")
        logger.debug(f":run: {self.name}: starting trimming thread..")
        self.rdv = threading.Event()
        self.trim_thread = threading.Thread(target=self.trim)
        self.trim_thread.start()
        self.shutdown_flag = threading.Event()
        logger.debug(f":run: {self.name}: ..done")

        nv = None
        try:
            while not self.shutdown_flag.is_set():
                logger.debug(f":run: {self.name}: listening..")
                dummy = self.now()
                nv = self.redis.bzpopmin(self.name, timeout=ZPOPMIN_TIMEOUT)
                if nv is None:
                    # logger.debug(f":run: {self.name}: bzpopmin timed out..")
                    continue
                numval = self.redis.zcard(self.name)
                logger.debug(f":run: {self.name}: {numval} items left in queue")
                now = self.now()
                logger.debug(f":run: {self.name}: it is now {df(now)}")
                wt = nv[2] - now       # wait time independant of time warp
                rwt = wt / self.speed  # real wait time, taking warp time into account
                if wt > 0:
                    logger.debug(f":run: {self.name}: need to send at {df(nv[2])}, waiting {td(wt)}, speed={self.speed}, waiting={round(rwt, 1)}")
                    if not self.rdv.wait(timeout=rwt):  # we timed out
                        logger.debug(f":run: {self.name}: sending..")
                        self.redis.publish(self.name, nv[1].decode('UTF-8'))
                        logger.debug(f":run: {self.name}: ..done")
                    else:  # we were instructed to not send
                        # put item back in queue
                        logger.debug(f":run: {self.name}: need trimming, push back on queue..")
                        self.redis.zadd(self.name, {nv[1]: nv[2]})
                        # this is not 100% correct: Some event of nextval array may have already be sent
                        # done. ok to trim
                        logger.debug(f":run: {self.name}: ok to trim..")
                        self.oktotrim.set()
                        # wait trimming completed
                        self.trimmingcompleted = threading.Event()
                        logger.debug(f":run: {self.name}: waiting trim completes..")
                        self.trimmingcompleted.wait()
                        logger.debug(f":run: {self.name}: trim completed, restarted")
                else:
                    logger.debug(f":run: {self.name}: should have sent at {df(nv[2])} ({td(wt)} sec. ago, rwt={rwt} sec. ago")
                    logger.debug(f":run: {self.name}: did not send {nv[1].decode('UTF-8')}")
        except KeyboardInterrupt:
            if nv is not None:
                logger.debug(f":run: {self.name}: keyboard interrupt, try to push poped item back on queue..")
                self.redis.zadd(self.name, {nv[1]: nv[2]})
                logger.debug(f":run: {self.name}: ..done")
            else:
                logger.debug(f":run: {self.name}: keyboard interrupt, nothing to push back on queue")
        finally:
            logger.debug(f":run: {self.name}: quitting..")
            self.redis.publish("Q"+self.name, "quit")
            logger.debug(f":run: {self.name}: ..waiting for trimmer..")
            self.trim_thread.join()
            logger.debug(f":run: {self.name}: ..bye")


# ##############################@@
# H Y P E R C A S T E R
#
class HyperCaster:
    """
    Starts a Broadcaster for each queue
    """
    def __init__(self):
        self.redis = redis.Redis(**REDIS_CONNECT)
        self.queues = {}
        self.pubsub = self.redis.pubsub()
        self.admin_queue_thread = None

        self.init()

    def init(self):
        self.queues = Queue.loadAllQueuesFromDB()
        for k in self.queues.values():
            self.start_queue(k)
        logger.debug(f":get_queues: {self.queues.keys()}")
        self.admin_queue_thread = threading.Thread(target=self.admin_queue)
        self.admin_queue_thread.start()

    def admin_queue(self):
        self.pubsub.subscribe(REDIS_DATABASE.QUEUES.value)
        logger.debug(":admin_queue: listening..")
        for message in self.pubsub.listen():
            msg = message["data"]
            if type(msg) == bytes:
                msg = msg.decode('UTF-8')
            logger.debug(f":admin_queue: received {msg}")
            if type(msg).__name__ == "str" and msg.startswith("new-queue:"):
                arr = msg.split(":")
                qn  = arr[1]
                if qn not in self.queues.keys():  # queue already exists, parameter changed, stop it first
                    self.queues[qn] = Queue.loadFromDB(qn)
                    self.start_queue(self.queues[qn])
                else:
                    logger.debug(f":admin_queue: queue {qn} already running, reseting")
                    oldsp = self.queues[qn].speed
                    oldst = self.queues[qn].starttime
                    oldbr = self.queues[qn].broadcaster
                    self.queues[qn] = Queue.loadFromDB(redis=self.redis, name=qn)
                    self.queues[qn].broadcaster = oldbr
                    oldbr.reset(redis=self.redis, speed=self.queues[qn].speed, starttime=self.queues[qn].starttime)
                    logger.debug(f":admin_queue: queue {qn} speed {self.queues[qn].speed} (was {oldsp})")
                    logger.debug(f":admin_queue: queue {qn} starttime {self.queues[qn].starttime} (was {oldst})")

            elif type(msg).__name__ == "str" and msg.startswith("del-queue:"):
                arr = msg.split(":")
                qn  = arr[1]
                if qn in self.queues.keys():
                    if not hasattr(self.queues[qn], "deleted"):  # queue already exists, parameter changed, stop it first
                        self.terminate_queue(qn)
                        self.queues[qn].deleted = True
                        logger.debug(f":admin_queue: queue {qn} terminated")
                    else:
                        logger.debug(f":admin_queue: queue {qn} already deleted")
            elif msg == "quit":
                logger.debug(":admin_queue: quitting..")
                return
            else:
                logger.debug(f":admin_queue: ignoring '{msg}'")

    def start_queue(self, queue):
        b = Broadcaster(queue.name, queue.speed, queue.starttime)
        self.queues[queue.name].broadcaster = b
        self.queues[queue.name].thread = threading.Thread(target=b.broadcast)
        self.queues[queue.name].thread.start()
        logger.debug(f":start_queue: {queue.name} started")

    def terminate_queue(self, queue):
        if hasattr(self.queues[queue], "broadcaster"):
            if hasattr(self.queues[queue].broadcaster, "shutdown_flag"):
                self.queues[queue].broadcaster.shutdown_flag.set()
                logger.debug(f":terminate_queue: {queue} notified")
            else:
                logger.warning(f":terminate_queue: {queue} has no shutdown_flag")
        else:
            logger.warning(f":terminate_queue: {queue} has no broadcaster")

    def terminate_all_queues(self):
        self.redis.publish(REDIS_DATABASE.QUEUES.value, "quit")
        for k in self.queues.keys():
            self.terminate_queue(k)

    def run(self):
        # rdv = threading.Event()
        # rdv.wait(timeout=180)
        # self.terminate_all_queues()

        try:
            logger.debug(f":run: running..")
        except KeyboardInterrupt:
            logger.debug(f":run: terminate all queues..")
            self.terminate_all_queues()
            logger.debug(f":run: ..done")
        finally:
            logger.debug(f":run: waiting all threads..")
            self.admin_queue_thread.join()
            logger.debug(f":run: ..bye")



