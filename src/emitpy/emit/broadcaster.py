from datetime import datetime, timedelta
import threading
import signal
import time
import redis
import logging
import json

from emitpy.constants import REDIS_DATABASE, ID_SEP
from emitpy.parameters import REDIS_CONNECT, BROADCASTER_HEARTHBEAT
from .queue import Queue, RUN, STOP, NEW_QUEUE, DELETE_QUEUE

# Queue name prefix
ADM_QUEUE_PREFIX = "adm:"
OUT_QUEUE_PREFIX = "emitpy:"  # could be ""

logger = logging.getLogger("Broadcaster")


# Utility functions for debugging time
def df(ts):
    return f"{datetime.fromtimestamp(ts).isoformat(timespec='seconds')} ({round(ts, 1)})"

def td(ts):
    return f"{timedelta(seconds=round(ts))} ({round(ts, 1)})"


# Delicate parameters, too dangerous to externalize
ZPOPMIN_TIMEOUT = 10  # secs
PING_FREQUENCY  = 6   # once every PING_FREQUENCY * ZPOPMIN_TIMEOUT seconds


QUIT = "quit"
NEW_DATA = "new-data"


# ##############################
# B R O A D C A S T E R
#
class Broadcaster:

    def __init__(self, redis, name: str, speed: float = 1, starttime: datetime = None):
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

        self.ping = PING_FREQUENCY
        self.heartbeat = BROADCASTER_HEARTHBEAT

        self.redis = redis
        self.pubsub = self.redis.pubsub()

        self.should_quit = False  # Emergency, dead-lock preventive shutdown.

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

    def getInfo(self):
        realnow = datetime.now()
        elapsed = realnow - (self.starttime() + self.timeshift)
        return {
            "now": realnow.isoformat(),
            "queue": self.name,
            "heartbeat": self.heartbeat,
            "starttime": self.starttime().isoformat(),
            "speed": self.speed,
            "timeshift": str(self.timeshift),
            "elapsed": str(elapsed),
            "queue-time": self.now(format_output=True)
        }

    def reset(self, speed: float = 1, starttime: datetime = None):
        self.speed = speed
        if starttime is not None:
            if type(starttime) == str:
                self._starttime = datetime.fromisoformat(starttime)
            else:
                self._starttime = starttime
            self.setTimeshift()

    def now(self, format_output: bool = False, verbose: bool = False):
        realnow = datetime.now()
        if self.speed == 1 and self.timeshift.total_seconds() == 0:
            newnow = realnow
            if verbose:
                logger.debug(f":now: {self.name}: no time speed, no time shift: new now: {df(newnow.timestamp())}")
            return newnow.timestamp() if not format_output else newnow.isoformat(timespec='seconds')

        if verbose:
            logger.debug(f":now: {self.name}: asked at {df(realnow.timestamp())})")
        elapsed = realnow - (self.starttime() + self.timeshift)  # time elapsed since setTimeshift().
        if verbose:
            logger.debug(f":now: {self.name}: real elapsed since start of queue: {elapsed})")
        if self.speed == 1:
            newnow = self.starttime() + elapsed
            if verbose:
                logger.debug(f":now: {self.name}: no time speed: new now: {df(newnow.timestamp())}")
        else:
            newdeltasec = elapsed.total_seconds() * self.speed
            newdelta = timedelta(seconds=newdeltasec)
            newnow = self.starttime() + newdelta
            if verbose:
                logger.debug(f":now: {self.name}: time speed {self.speed}: new elapsed: {newdelta}, new now={df(newnow.timestamp())}")
        return newnow.timestamp() if not format_output else newnow.isoformat(timespec='seconds')

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
        self.pubsub.subscribe(ADM_QUEUE_PREFIX+self.name)
        logger.debug(f":trim: {self.name}: listening..")
        for message in self.pubsub.get_message(timeout=10.0):
            if message is not None and type(message) != str and "data" in message:
                msg = message["data"]
                if type(msg) == bytes:
                    msg = msg.decode('UTF-8')
                logger.debug(f":trim: {self.name}: received {msg}")
                if msg == NEW_DATA:
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
                elif msg == QUIT:
                    logger.debug(f":trim: {self.name}: quitting..")
                    return
                else:
                    logger.debug(f":trim: {self.name}: ignoring '{msg}'")
            else: # timed out
                logger.debug(f":trim: {self.name}: trip timeout '{self.should_quit}'")
                if self.should_quit:
                    return

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
        ping = 0
        try:
            while not self.shutdown_flag.is_set():
                if self.heartbeat:
                    logger.debug(f":run: {self.name}: listening..")
                dummy = self.now(format_output=True)
                nv = self.redis.bzpopmin(self.name, timeout=ZPOPMIN_TIMEOUT)
                if nv is None:
                    if self.ping > 0 and ping < 0:
                        logger.debug(f":run: {self.name}: pinging..")
                        self.redis.publish(OUT_QUEUE_PREFIX+self.name, json.dumps({
                            "ping": datetime.now().isoformat(),
                            "broadcaster": self.getInfo()
                        }))
                        ping = self.ping
                    elif self.ping > 0:
                        ping = ping - 1
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
                        self.redis.publish(OUT_QUEUE_PREFIX+self.name, nv[1].decode('UTF-8'))
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
            self.redis.publish(ADM_QUEUE_PREFIX+self.name, QUIT)
            logger.debug(f":run: {self.name}: ..waiting for trimmer..")
            self.trim_thread.join()
            logger.debug(f":run: {self.name}: ..bye")


# ##############################@@
# H Y P E R C A S T E R
#
class Hypercaster:
    """
    Starts a Broadcaster for each queue
    """

    _instance = None
    _lock = threading.Lock()

    @classmethod
    def __new__(cls, *args, **kwargs):
        # https://medium.com/analytics-vidhya/how-to-create-a-thread-safe-singleton-class-in-python-822e1170a7f6
        if not cls._instance:
            with cls._lock:
                # another thread could have created the instance
                # before we acquired the lock. So check that the
                # instance is still nonexistent.
                if not cls._instance:
                    cls._instance = super(Hypercaster, cls).__new__(cls)
        return cls._instance


    def __init__(self):
        self.redis_pool = redis.ConnectionPool(**REDIS_CONNECT)
        self.redis = redis.Redis(connection_pool=self.redis_pool)
        self.queues = {}
        self.pubsub = self.redis.pubsub()
        self.admin_queue_thread = None
        self.should_quit = False

        self.init()

    def init(self):
        self.queues = Queue.loadAllQueuesFromDB(self.redis)
        for k in self.queues.values():
            self.start_queue(k)
        self.admin_queue_thread = threading.Thread(target=self.admin_queue)
        self.admin_queue_thread.start()
        logger.debug(f"Hypercaster:init: {self.queues.keys()}")

    def start_queue(self, queue):
        if self.queues[queue.name].status == RUN:
            b = Broadcaster(redis.Redis(connection_pool=self.redis_pool), queue.name, queue.speed, queue.starttime)
            self.queues[queue.name].broadcaster = b
            self.queues[queue.name].broadcaster.should_quit = False
            self.queues[queue.name].thread = threading.Thread(target=b.broadcast)
            self.queues[queue.name].thread.start()
            logger.debug(f"Hypercaster:start_queue: {queue.name} started")
        else:
            logger.warning(f"Hypercaster:start_queue: {queue.name} is stopped")

    def terminate_queue(self, queue):
        if hasattr(self.queues[queue], "broadcaster"):
            if hasattr(self.queues[queue].broadcaster, "shutdown_flag"):
                self.queues[queue].broadcaster.should_quit = True
                self.queues[queue].broadcaster.shutdown_flag.set()
                # now that we have notified the broadcaster, we don't need it anymore
                self.queues[queue].broadcaster = None
                logger.debug(f"Hypercaster:terminate_queue: {queue} notified")
            else:
                logger.warning(f"Hypercaster:terminate_queue: {queue} has no shutdown_flag")
        else:
            logger.warning(f"Hypercaster:terminate_queue: {queue} has no broadcaster")

    def terminate_all_queues(self):
        self.redis.publish(REDIS_DATABASE.QUEUES.value, QUIT)
        for k in self.queues.keys():
            self.terminate_queue(k)

    def admin_queue(self):
        # redis events:
        # :run: received {'type': 'pmessage', 'pattern': b'__keyspace@0__:*', 'channel': b'__keyspace@0__:queues', 'data': b'sadd'}
        # :run: received {'type': 'pmessage', 'pattern': b'__keyspace@0__:*', 'channel': b'__keyspace@0__:queues', 'data': b'srem'}
        # :run: received {'type': 'pmessage', 'pattern': b'__keyspace@0__:*', 'channel': b'__keyspace@0__:queues', 'data': b'del'}
        # :run: received {'type': 'pmessage', 'pattern': b'__keyspace@0__:*', 'channel': b'__keyspace@0__:queues:test', 'data': b'del'}
        self.should_quit = False
        self.pubsub.subscribe(REDIS_DATABASE.QUEUES.value)
        logger.debug("Hypercaster:admin_queue: listening..")
        for message in self.pubsub.get_message(timeout=10.0):
            if message is not None and type(message) != str and "data" in message:
                msg = message["data"]
                if type(msg) == bytes:
                    msg = msg.decode("UTF-8")
                logger.debug(f"Hypercaster:admin_queue: received {msg}")
                if type(msg).__name__ == "str" and msg.startswith(NEW_QUEUE+ID_SEP):
                    arr = msg.split(":")
                    qn  = arr[1]
                    if qn not in self.queues.keys():
                        self.queues[qn] = Queue.loadFromDB(name=qn, redis=self.redis)
                        self.start_queue(self.queues[qn])
                    else:   # queue already exists, parameter changed, stop it first
                        logger.debug(f":admin_queue: queue {qn} already running, reseting..")
                        oldsp = self.queues[qn].speed
                        oldst = self.queues[qn].starttime
                        # there is no broadcaster if queue was not started
                        oldbr = self.queues[qn].broadcaster if hasattr(self.queues[qn], "broadcaster") else None
                        self.queues[qn] = Queue.loadFromDB(redis=self.redis, name=qn)
                        if oldbr is not None and self.queues[qn].status == STOP:
                            # queue was working beofre and is now stopped: replaces broadcaster and terminates it
                            self.queues[qn].broadcaster = oldbr
                            self.terminate_queue(qn)
                            logger.debug(f"Hypercaster:admin_queue: ..queue {qn} stopped")
                        elif oldbr is None and self.queues[qn].status == RUN:
                            # queue was not working before and is now started
                            self.start_queue(self.queues[qn])
                            logger.debug(f"Hypercaster:admin_queue: ..queue {qn} started")
                        elif oldbr is None and self.queues[qn].status == STOP:
                            # queue was not working before and is now started
                            logger.debug(f"Hypercaster:admin_queue: ..queue {qn} added but stopped")
                        else:
                            # queue was working before, will continue to work bbut some parameters are reset
                            oldbr.reset(speed=self.queues[qn].speed, starttime=self.queues[qn].starttime)
                            logger.debug(f"Hypercaster:admin_queue: .. queue {qn} speed {self.queues[qn].speed} (was {oldsp}) " +
                                         f"starttime {self.queues[qn].starttime} (was {oldst}) reset")

                elif type(msg).__name__ == "str" and msg.startswith(DELETE_QUEUE+ID_SEP):
                    arr = msg.split(":")
                    qn  = arr[1]
                    if qn in self.queues.keys():
                        if not hasattr(self.queues[qn], "deleted"):  # queue already exists, parameter changed, stop it first
                            self.terminate_queue(qn)
                            self.queues[qn].deleted = True
                            logger.debug(f"Hypercaster:admin_queue: queue {qn} terminated")
                        else:
                            logger.debug(f"Hypercaster:admin_queue: queue {qn} already deleted")
                elif msg == QUIT:
                    logger.debug("Hypercaster:admin_queue: quitting..")
                    return
                else:
                    logger.debug(f"Hypercaster:admin_queue: ignoring '{msg}'")
            else:  # timed out
                logger.debug(f"Hypercaster:admin_queue: timed out {self.should_quit}")
                if self.should_quit:
                    logger.debug(f"Hypercaster:admin_queue: should quit, quitting..")
                    return

    def run(self):
        try:
            self.admin_queue_thread.start()
            logger.debug(f"Hypercaster:run: running..")
        except KeyboardInterrupt:
            logger.debug(f"Hypercaster:run: terminate all queues..")
            self.terminate_all_queues()
            self.should_quit = True
            logger.debug(f":run: ..done")
        finally:
            logger.debug(f"Hypercaster:run: waiting all threads..")
            self.admin_queue_thread.join()
            logger.debug(f"Hypercaster:run: ..bye")
