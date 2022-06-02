from datetime import datetime, timedelta
import threading
import signal
import time
import redis
import logging
import json
import socket

from emitpy.constants import REDIS_DATABASE, ID_SEP, LIVETRAFFIC_QUEUE
from emitpy.parameters import REDIS_CONNECT, BROADCASTER_HEARTBEAT
from emitpy.parameters import XPLANE_HOSTNAME, XPLANE_PORT

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
LISTEN_TIMEOUT = 10.0


# Internal keywords
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
        self.heartbeat = BROADCASTER_HEARTBEAT

        self.redis = redis
        self.pubsub = self.redis.pubsub()

        self.oktotrim = None

        self.setTimeshift()
        self.shutdown_flag = threading.Event()


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
        """
        Removes elements in sortedset that are outdated for this queue's time.
        """
        now = self.now()
        logger.debug(f":_do_trim: {self.name}: {df(now)}): trimming..")
        oldones = self.redis.zrangebyscore(self.name, min=0, max=now)
        if oldones and len(oldones) > 0:
            self.redis.zrem(self.name, *oldones)
            logger.debug(f":_do_trim: {self.name}: ..removed {len(oldones)} messages..done")
        else:
            logger.debug(f":_do_trim: {self.name}: nothing to remove ..done")

    def trim(self):
        """
        Wrapper to prevent new "pop" while trimming the queue.
        If new elements are added while, it does not matter because they will be trimmed at the end of their insertion.
        """
        self.pubsub.subscribe(ADM_QUEUE_PREFIX+self.name)
        logger.debug(f":trim: {self.name}: listening..")
        while not self.shutdown_flag.is_set():
            if self.heartbeat:
                logger.debug(f":trim: {self.name}: listening..")
            # logger.debug(f":trim: {self.name}: waiting for message (with timeout {LISTEN_TIMEOUT} secs.)..")
            message = self.pubsub.get_message(timeout=LISTEN_TIMEOUT)
            if message is not None:
                logger.debug(f":trim: got raw {message}, of type {type(message)}, processing..")
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
                    self.oktotrim = None
                    self._do_trim()
                    logger.debug(f":trim: {self.name}: tell sender to restart, provide new blocking event..")
                    self.rdv = threading.Event()
                    self.trimmingcompleted.set()
                    logger.debug(f":trim: {self.name}: listening again..")
                elif msg == QUIT:
                    self.pubsub.unsubscribe(ADM_QUEUE_PREFIX+self.name)
                    self.shutdown_flag.set()
                    logger.debug(f":trim: {self.name}: quitting..")
                    logger.debug(f":trim: {self.name}: ..bye")
                    return
                else:
                    logger.debug(f":trim: {self.name}: ignoring '{msg}'")
            # else: # timed out
            #     logger.debug(f":trim: {self.name}: trim timeout, should quit? {self.shutdown_flag.is_set()}")

        logger.debug(f":trim: {self.name}: quitting..")
        logger.debug(f":trim: {self.name}: ..bye")


    def send_data(self, data: str) -> int:
        self.redis.publish(OUT_QUEUE_PREFIX+self.name, data)
        return 0


    def broadcast(self):
        """
        Pop elements from the sortedset at requested time and publish them on pubsub queue.
        """
        logger.debug(f":broadcast: {self.name}: pre-start trimming..")
        self._do_trim()
        logger.debug(f":broadcast: {self.name}: ..done")
        logger.debug(f":broadcast: {self.name}: starting trimming thread..")
        self.rdv = threading.Event()
        self.shutdown_flag = threading.Event()
        self.trim_thread = threading.Thread(target=self.trim)
        self.trim_thread.start()
        logger.debug(f":broadcast: {self.name}: ..done")

        currval = None
        ping = 0
        last_sent = datetime.now() - timedelta(seconds=1)
        # Wrapped in a big try:/except: to catch errors and keyboard interrupts.
        try:
            while not self.shutdown_flag.is_set():
                dummy = self.now(format_output=True)

                if self.heartbeat: # and last_sent < datetime.now()
                    logger.debug(f":broadcast: {self.name}: listening..")

                currval = self.redis.bzpopmin(self.name, timeout=ZPOPMIN_TIMEOUT)
                if currval is None:
                    # @todo: Ping in another thread
                    # if self.ping > 0 and ping < 0:
                    #     logger.debug(f":broadcast: {self.name}: pinging..")
                    #     self.redis.publish(OUT_QUEUE_PREFIX+self.name, json.dumps({
                    #         "ping": datetime.now().isoformat(),
                    #         "broadcaster": self.getInfo()
                    #     }))
                    #     ping = self.ping
                    # elif self.ping > 0:
                    #     ping = ping - 1
                    logger.debug(f":broadcast: {self.name}: bzpopmin timed out..")
                    continue

                numval = self.redis.zcard(self.name)
                # logger.debug(f":broadcast: {self.name}: {numval} items left in queue")
                now = self.now()
                # logger.debug(f":broadcast: {self.name}: it is now {df(now)}")
                # logger.debug(f":broadcast: {self.name}: at {df(now)}: {numval} in queue")
                timetowait = currval[2] - now       # wait time independant of time warp
                realtimetowait = timetowait / self.speed  # real wait time, taking warp time into account
                if timetowait < 0:  # there are things on the queue that don't need to be sent, let's trim:
                    # the item we poped out is older than the queue time, we do not send it
                    logger.debug(f":broadcast: {self.name}: awake by old event. Trim other old events..")

                    if self.shutdown_flag.is_set():
                        logger.debug(f":broadcast: {self.name}: awake to quit, quitting..")
                        return

                    # wait trimming of old events completes
                    self.trimmingcompleted = threading.Event()
                    logger.debug(f":broadcast: {self.name}: waiting for trimmer..")
                    self.rdv.wait()
                    self.oktotrim.set()
                    logger.debug(f":broadcast: {self.name}: ..waiting trim completes..")
                    self.trimmingcompleted.wait()
                    logger.debug(f":broadcast: {self.name}: ..trim older events completed, restarted listening")

                else:  # we need to send later, let's wait
                    logger.debug(f":broadcast: {self.name}: need to send at {df(currval[2])}, waiting {td(timetowait)}, speed={self.speed}, waiting={round(realtimetowait, 1)}")

                    if not self.rdv.wait(timeout=realtimetowait):
                        # we timed out, we need to send
                        logger.debug(f":broadcast: {self.name}: sending..")
                        r = self.send_data(currval[1].decode('UTF-8'))
                        if r != 0:
                            logger.warning(f":send_data: did not complete successfully (errcode={r})")
                        # self.redis.publish(OUT_QUEUE_PREFIX+self.name, currval[1].decode('UTF-8'))
                        currval = None  # currval was sent, we don't need to push it back or anything like that
                        logger.debug(f":broadcast: {self.name}: ..done")
                    else:
                        # we were instructed to not send
                        # put current event back in queue
                        if currval is not None:
                            logger.debug(f":broadcast: {self.name}: awake to not send, push current event back on queue..")
                            self.redis.zadd(self.name, {currval[1]: currval[2]})
                            logger.debug(f":broadcast: {self.name}: ..done")

                        if self.shutdown_flag.is_set():
                            logger.debug(f":broadcast: {self.name}: awake to quit, quitting..")
                            return

                        # this is not 100% correct: Some event of nextval array may have already be sent
                        logger.debug(f":broadcast: {self.name}: awake to trim, ok to trim..")
                        # wait trimming completed
                        self.trimmingcompleted = threading.Event()
                        self.oktotrim.set()
                        logger.debug(f":broadcast: {self.name}: ..waiting trim completes..")
                        self.trimmingcompleted.wait()
                        logger.debug(f":broadcast: {self.name}: ..trim completed, restarted listening")

        except KeyboardInterrupt:
            if currval is not None:
                logger.debug(f":broadcast: {self.name}: keyboard interrupt, trying to push poped item back on queue..")
                self.redis.zadd(self.name, {currval[1]: currval[2]})
                logger.debug(f":broadcast: {self.name}: ..done")
            else:
                logger.debug(f":broadcast: {self.name}: keyboard interrupt, nothing to push back on queue")
        finally:
            logger.debug(f":broadcast: {self.name}: quitting..")
            self.redis.publish(ADM_QUEUE_PREFIX+self.name, QUIT)
            quitted = False
            tries = 3
            while not quitted:
                if self.trim_thread.is_alive() and tries > 0:
                    logger.debug(f":broadcast: {self.name}: sending quit instruction..")
                    self.redis.publish(ADM_QUEUE_PREFIX+self.name, QUIT)
                    logger.debug(f":broadcast: {self.name}: ..waiting for trimmer..")
                    self.trim_thread.join(timeout=2 * LISTEN_TIMEOUT)
                    logger.debug(f":broadcast: {self.name}: join timed out")
                    tries = tries - 1
                else:
                    if self.trim_thread.is_alive() and tries < 0:
                        logger.warning(f":broadcast: {self.name}: fed up waiting, trim_thread still alive, force quit..")
                    quitted = True
            logger.debug(f":broadcast: {self.name}: ..bye")


class LiveTrafficForwarder(Broadcaster):

    def __init__(self, redis):
        Broadcaster.__init__(self, redis=redis, name=LIVETRAFFIC_QUEUE)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        logger.debug(f"LiveTrafficForwarder::__init__: inited")

    # def compWaitTS(ts_s: str) -> str:
    #     global _tsDiff
    #     # current time and convert timestamp
    #     now = int(time.time())
    #     ts = int(ts_s)
    #     # First time called? -> compute initial timestamp difference
    #     if not _tsDiff:
    #         _tsDiff = now - ts - args.bufPeriod
    #         if args.verbose:
    #             print ("Timestamp difference: {}".format(_tsDiff))
    #     # What's the required timestamp to wait for and then return?
    #     ts += _tsDiff
    #     # if that's in the future then wait
    #     if (ts > now):
    #         if args.verbose:
    #             print ("Waiting for {} seconds...".format(ts-now), end='\r')
    #         time.sleep (ts-now)
    #     # Adjust returned timestamp value for historic timestamp
    #     ts -= args.historic
    #     return str(ts)

    def send_data(self, data: str) -> int:
        fields = data.split(',')
        if len(fields) != 15:
            logger.warning(f"Found {len(fields)} fields, expected 15, in line {data}")
            return 1
        # Update and wait for timestamp
        # fields[14] = compWaitTS(fields[14])  # this is done in our own broadcaster :-)
        datagram = ','.join(fields)
        self.sock.sendto(datagram.encode('ascii'), (XPLANE_HOSTNAME, XPLANE_PORT))
        fields[1] = f"{int(fields[1]):x}"
        logger.debug(f":send_data: {datagram}")
        logger.debug(f":send_data: ac:{fields[1]}: alt={fields[4]} ft, hdg={fields[7]}, speed={fields[8]} kn, vspeed={fields[5]} ft/min")
        return 0


# ##############################@@
# H Y P E R C A S T E R
#
hyperlogger = logging.getLogger("Hypercaster")

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
        self.shutdown_flag = threading.Event()
        self.heartbeat = BROADCASTER_HEARTBEAT

        self.init()

    def init(self):
        self.queues = Queue.loadAllQueuesFromDB(self.redis)
        for k in self.queues.values():
            self.start_queue(k)
        self.admin_queue_thread = threading.Thread(target=self.admin_queue)
        self.admin_queue_thread.start()
        hyperlogger.debug(f":init: {self.queues.keys()}")

    def start_queue(self, queue):
        if self.queues[queue.name].status == RUN:
            b = None
            if queue.name == LIVETRAFFIC_QUEUE:
                b = LiveTrafficForwarder(redis.Redis(connection_pool=self.redis_pool))
                hyperlogger.debug(f":start_queue: LiveTrafficForwarder started")
            else:
                b = Broadcaster(redis.Redis(connection_pool=self.redis_pool), queue.name, queue.speed, queue.starttime)
            self.queues[queue.name].broadcaster = b
            self.queues[queue.name].thread = threading.Thread(target=b.broadcast)
            self.queues[queue.name].thread.start()
            hyperlogger.debug(f":start_queue: {queue.name} started")
        else:
            hyperlogger.warning(f":start_queue: {queue.name} is stopped")

    def terminate_queue(self, queue):
        if hasattr(self.queues[queue], "broadcaster"):
            if hasattr(self.queues[queue].broadcaster, "shutdown_flag"):
                self.queues[queue].broadcaster.shutdown_flag.set()
                hyperlogger.debug(f":terminate_queue: {queue} awakening wait() on send..")
                self.queues[queue].broadcaster.rdv.set()
                # now that we have notified the broadcaster, we don't need it anymore
                self.queues[queue].broadcaster = None
                hyperlogger.debug(f":terminate_queue: {queue} notified")
            else:  # @todo: Why do we sometimes get here??
                hyperlogger.warning(f":terminate_queue: {queue} has no shutdown_flag")
        else:
            hyperlogger.warning(f":terminate_queue: {queue} has no broadcaster")

    def terminate_all_queues(self):
        hyperlogger.debug(f":terminate_all_queues: notifying..")
        for k in self.queues.keys():
            hyperlogger.debug(f":terminate_all_queues: notifying {k}..")
            self.terminate_queue(k)
        hyperlogger.debug(f":terminate_all_queues: notifying admin..")
        self.redis.publish(REDIS_DATABASE.QUEUES.value, QUIT)
        hyperlogger.debug(f":terminate_all_queues: ..done")

    def admin_queue(self):
        # redis events:
        # :admin_queue: received {'type': 'pmessage', 'pattern': b'__keyspace@0__:*', 'channel': b'__keyspace@0__:queues', 'data': b'sadd'}
        # :admin_queue: received {'type': 'pmessage', 'pattern': b'__keyspace@0__:*', 'channel': b'__keyspace@0__:queues', 'data': b'srem'}
        # :admin_queue: received {'type': 'pmessage', 'pattern': b'__keyspace@0__:*', 'channel': b'__keyspace@0__:queues', 'data': b'del'}
        # :admin_queue: received {'type': 'pmessage', 'pattern': b'__keyspace@0__:*', 'channel': b'__keyspace@0__:queues:test', 'data': b'del'}
        self.pubsub.subscribe(REDIS_DATABASE.QUEUES.value)
        hyperlogger.debug(":admin_queue: listening..")

        while not self.shutdown_flag.is_set():
            if self.heartbeat: # and last_sent < datetime.now()
                logger.debug(f":admin_queue: listening..")
            message = self.pubsub.get_message(timeout=LISTEN_TIMEOUT)
            if message is not None and type(message) != str and "data" in message:
                msg = message["data"]
                if type(msg) == bytes:
                    msg = msg.decode("UTF-8")
                hyperlogger.debug(f":admin_queue: received {msg}")
                if type(msg).__name__ == "str" and msg.startswith(NEW_QUEUE+ID_SEP):
                    arr = msg.split(ID_SEP)
                    qn  = arr[1]
                    if qn not in self.queues.keys():
                        self.queues[qn] = Queue.loadFromDB(name=qn, redis=self.redis)
                        self.start_queue(self.queues[qn])
                    else:   # queue already exists, parameter changed, stop it first
                        hyperlogger.debug(f":admin_queue: queue {qn} already running, reseting..")
                        oldsp = self.queues[qn].speed
                        oldst = self.queues[qn].starttime
                        # there is no broadcaster if queue was not started
                        oldbr = self.queues[qn].broadcaster if hasattr(self.queues[qn], "broadcaster") else None
                        # if oldbr is None:
                        #     hyperlogger.debug(f":admin_queue: ..queue {qn} had no broadcaster..")
                        # else:
                        #     hyperlogger.debug(f":admin_queue: ..queue reusing {qn} broadcaster..")
                        self.queues[qn] = Queue.loadFromDB(redis=self.redis, name=qn)
                        if oldbr is not None and self.queues[qn].status == STOP:
                            # queue was working beofre and is now stopped: replaces broadcaster and terminates it
                            self.queues[qn].broadcaster = oldbr
                            self.terminate_queue(qn)
                            hyperlogger.debug(f":admin_queue: ..queue {qn} stopped")
                        elif oldbr is None and self.queues[qn].status == RUN:
                            # queue was not working before and is now started
                            self.start_queue(self.queues[qn])
                            hyperlogger.debug(f":admin_queue: ..queue {qn} started")
                        elif oldbr is None and self.queues[qn].status == STOP:
                            # queue was not working before and is now started
                            hyperlogger.debug(f":admin_queue: ..queue {qn} added but stopped")
                        else:
                            # queue was working before, will continue to work bbut some parameters are reset
                            self.queues[qn].broadcaster = oldbr
                            oldbr.reset(speed=self.queues[qn].speed, starttime=self.queues[qn].starttime)
                            hyperlogger.debug(f":admin_queue: .. queue {qn} speed {self.queues[qn].speed} (was {oldsp}) " +
                                         f"starttime {self.queues[qn].starttime} (was {oldst}) reset")
                        hyperlogger.debug(f":admin_queue: ..done")

                elif type(msg).__name__ == "str" and msg.startswith(DELETE_QUEUE+ID_SEP):
                    arr = msg.split(ID_SEP)
                    qn  = arr[1]
                    if qn in self.queues.keys():
                        if not hasattr(self.queues[qn], "deleted"):  # queue already exists, parameter changed, stop it first
                            self.terminate_queue(qn)
                            self.queues[qn].deleted = True
                            hyperlogger.debug(f":admin_queue: queue {qn} terminated")
                        else:
                            hyperlogger.debug(f":admin_queue: queue {qn} already deleted")
                elif msg == QUIT:
                    hyperlogger.debug(":admin_queue: quitting..")
                    self.pubsub.unsubscribe(REDIS_DATABASE.QUEUES.value)
                    return
                else:
                    hyperlogger.debug(f":admin_queue: ignoring '{msg}'")
            else:  # timed out
                # hyperlogger.debug(f":admin_queue: timed out, should quit? {self.shutdown_flag.is_set()}")
                if self.shutdown_flag.is_set():
                    hyperlogger.debug(f":admin_queue: should quit, quitting..")
                    self.pubsub.unsubscribe(REDIS_DATABASE.QUEUES.value)
                    return

    def run(self):
        try:
            self.admin_queue_thread.start()
            hyperlogger.debug(f":run: running..")
        except KeyboardInterrupt:
            hyperlogger.debug(f":run: terminate all queues..")
            self.terminate_all_queues()
            self.shutdown_flag.set()  # reminder to self!
            hyperlogger.debug(f":run: ..done")
        finally:
            hyperlogger.debug(f":run: waiting all threads to finish..")
            self.admin_queue_thread.join()
            hyperlogger.debug(f":run: ..done. Bye")
