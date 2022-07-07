from datetime import datetime, timedelta
import threading
import signal
import time
import redis
import logging
import json
import socket

from emitpy.constants import REDIS_DATABASE, ID_SEP, LIVETRAFFIC_QUEUE, QUEUE_PREFIX, QUEUE_DATA
from emitpy.utils import key_path
from emitpy.parameters import REDIS_CONNECT, BROADCASTER_HEARTBEAT
from emitpy.parameters import XPLANE_FEED, XPLANE_HOSTNAME, XPLANE_PORT

from .queue import Queue, RUN, STOP, QUIT

QUIT_KEY = key_path(REDIS_DATABASE.QUEUES.value, QUIT)

logger = logging.getLogger("Broadcaster")


# Utility functions for debugging time and printing timestamp nicely
def df(ts, tz = None):
    return f"{datetime.fromtimestamp(ts).astimezone(tz=tz).isoformat(timespec='seconds')} (ts={round(ts, 1)})"

def td(ts):
    return f"{timedelta(seconds=round(ts))} ({round(ts, 1)})"


# ##############################
# C O N F I G
#
# Delicate parameters, too dangerous to externalize
#
ZPOPMIN_TIMEOUT = 5.0  # secs
LISTEN_TIMEOUT  = 5.0
PING_FREQUENCY  = 10.0 # once every PING_FREQUENCY * ZPOPMIN_TIMEOUT seconds

# MAXBACKLOGSECS is the maximum negative time we tolerate
# for sending events late (in seconds)
MAXBACKLOGSECS  = -20  # 0 is too critical, but MUST be <=0


# ##############################
# B R O A D C A S T E R
#
class Broadcaster:
    """
    The Broadcaster pops items from the sorted set, reads the timestamp,
    and publish items at the right time.
    Also trims the sorted set when events older than the "queue time" are found.
    """

    def __init__(self, redis, name: str, speed: float = 1, starttime: datetime = None):
        self.name = name

        self.speed = speed
        if starttime is None:
            self._starttime = datetime.now().astimezone()
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

        self.oktoreset = None
        self.resetcompleted = None


    def setTimeshift(self):
        self.timeshift = datetime.now().astimezone() - self.starttime()  # timedelta
        if self.timeshift < timedelta(seconds=10):
            self.timeshift = timedelta(seconds=0)
        logger.debug(f":setTimeshift: {self.name}: timeshift: {self.timeshift}, now: {df(datetime.now().timestamp())}, queue time: {df(self.now())}")
        return self.timeshift


    def starttime(self):
        if self._starttime is None:
            return datetime.now().astimezone()  # should never happen...
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
        # We need to ask the broadcaster to stop, put poped item back in queue
        logger.debug(f":reset: prepare..")
        self.oktoreset = threading.Event()
        logger.debug(f":reset: ..ready. wake up broadcaster..")
        self.rdv.set()
        logger.debug(f":reset: ..wait for broadcaster to block..")
        self.oktoreset.wait()
        self.oktoreset = None
        logger.debug(f":reset: ..freed, resetting..")
        ## _do_reset():
        self.speed = speed
        if starttime is not None:
            if type(starttime) == str:
                self._starttime = datetime.fromisoformat(starttime)
            else:
                self._starttime = starttime
            self.setTimeshift()
        ##
        logger.debug(f":reset: ..reset, tell broadcaster to restart..")
        self.rdv = threading.Event()
        self.resetcompleted.set()
        logger.debug(f":reset: ..cleaned, done")


    def now(self, format_output: bool = False, verbose: bool = False):
        realnow = datetime.now().astimezone()
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


    def _do_trim(self, ident=None):
        """
        Removes elements in sortedset that are outdated for this queue's time.
        """
        now = self.now()
        msg = "" if ident is None else f"{ident}:"
        logger.debug(f":_do_trim: {self.name}:{msg} {df(now)}: trimming..")
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
        pattern = "__keyspace@0__:"+self.name
        self.pubsub.subscribe(pattern)

        logger.info(f":trim: {self.name}: starting..")

        while not self.shutdown_flag.is_set():

            if self.heartbeat:
                logger.debug(f":trim: {self.name}: listening..")

            # logger.debug(f":trim: {self.name}: waiting for message (with timeout {LISTEN_TIMEOUT} secs.)..")
            # "pmessage","__key*__:*","__keyspace@0__:test","zadd"
            message = self.pubsub.get_message(timeout=LISTEN_TIMEOUT)
            if message is not None and type(message) != str and "data" in message:

                # logger.debug(f":trim: analyzing {message}..")

                ty = message["type"]
                if type(ty) == bytes:
                    ty = ty.decode("UTF-8")
                if ty != "message":
                    # logger.debug(f":trim: message type is not pmessage, ignoring")
                    continue

                ty = message["pattern"]
                if type(ty) == bytes:
                    ty = ty.decode("UTF-8")
                if ty != None:
                    # logger.debug(f":trim: pattern is not as expected ({ty} vs {pattern}), ignoring")
                    continue

                action = message["data"]
                if type(action) == bytes:
                    action = action.decode("UTF-8")

                if action not in ["zadd"]:
                    # logger.debug(f":admin_queue: ignoring action {action}")
                    continue

                queuestr = message["channel"]
                if type(queuestr) == bytes:
                    queuestr = queuestr.decode("UTF-8")
                qn = queuestr.split(ID_SEP)[-1]

                logger.debug(f":admin_queue: processing {action} {qn}..")


                if action == "zadd":
                    logger.debug(f":trim: {self.name}: ask sender to stop..")
                    # ask run() to stop sending:
                    self.oktotrim = threading.Event()
                    self.rdv.set()
                    logger.debug(f":trim: {self.name}: wait sender has stopped..")
                    self.oktotrim.wait()
                    self.oktotrim = None
                    self._do_trim(ident=2)
                    logger.debug(f":trim: {self.name}: tell sender to restart, provide new blocking event..")
                    self.rdv = threading.Event()
                    self.trimmingcompleted.set()
                    logger.info(f":trim: {self.name}: listening again..")

                else:
                    logger.debug(f":trim: {self.name}: ignoring '{msg}'")

        self.pubsub.unsubscribe(pattern)
        logger.info(f":trim: {self.name}: ..bye")


    def send_data(self, data: str) -> int:
        # l = min(30, len(data))
        # logger.debug(f":send_data: '{data[0:l]}'...")
        self.redis.publish(QUEUE_PREFIX+self.name, data)
        return 0


    def broadcast(self):
        """
        Pop elements from the sortedset at requested time and publish them on pubsub queue.
        """
        def pushback(item):
            # Trick to NOT zadd on self.name
            kn = key_path(QUEUE_DATA, self.name)
            self.redis.zadd(kn+"-TMP", item)
            self.redis.zunionstore(kn, [kn, kn+"-TMP"])
            self.redis.delete(self.name+"-TMP")
            # self.redis.zadd(self.name, {currval[1]: currval[2]})

        global MAXBACKLOGSECS  # ??
        if MAXBACKLOGSECS > 0:
            MAXBACKLOGSECS = - MAXBACKLOGSECS  # MUST be <=0 I said

        tz = self._starttime.tzinfo if hasattr(self._starttime, "tzinfo") else None

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

        logger.info(f":broadcast: {self.name}: starting..")

        # Wrapped in a big try:/except: to catch errors and keyboard interrupts.
        try:
            while not self.shutdown_flag.is_set():
                dummy = self.now(format_output=True)

                if self.oktotrim is not None:
                    if not self.oktotrim.is_set():
                        logger.warning(f":broadcast: {self.name}: trimmer is waiting, releasing..")
                        self.trimmingcompleted = threading.Event()
                        self.oktotrim.set()
                        logger.warning(f":broadcast: {self.name}: ..waiting trim completes..")
                        self.trimmingcompleted.wait()
                        # self.rdv = threading.Event()  # done in trim()
                        logger.warning(f":broadcast: {self.name}: ..trim completed, restarting")
                        continue
                    else:
                        logger.error(f":broadcast: {self.name}: trimmer is waiting but not set")

                if self.heartbeat: # and last_sent < datetime.now()
                    logger.debug(f":broadcast: {self.name}: listening..")

                currval = self.redis.bzpopmin(Queue.mkDataKey(self.name), timeout=ZPOPMIN_TIMEOUT)

                if currval is None:
                    # we may have some reset work to do
                    if self.oktoreset is not None: # Is it a reset() request?
                        logger.info(f":broadcast: {self.name}: bzpop timed out, reset requested. resetting..")
                        self.resetcompleted = threading.Event()
                        self.oktoreset.set()
                        logger.debug(f":broadcast: {self.name}: ..waiting reset completes..")
                        self.resetcompleted.wait()
                        # self.rdv = threading.Event()  # done in reset()
                        logger.info(f":broadcast: {self.name}: ..reset completed, restarting")
                    # else:
                    #     logger.debug(f":broadcast: {self.name}: nothing to send, bzpopmin timed out..")
                    continue

                numval = self.redis.zcard(self.name)
                # logger.debug(f":broadcast: {self.name}: {numval} items left in queue")
                pretxt = f"{numval} items left in queue,"
                now = self.now()
                # logger.debug(f":broadcast: {self.name}: it is now {df(now)}")
                # logger.debug(f":broadcast: {self.name}: at {df(now)}: {numval} in queue")
                timetowait = currval[2] - now       # wait time independant of time warp
                realtimetowait = timetowait / self.speed  # real wait time, taking warp time into account

                if timetowait < 0:
                    # there is a thing on top that should have be sent earlier
                    # me be we were busy doing something else, and just need to catchup.
                    # Example: 2 events just a few millisecs apart
                    logger.debug(f":broadcast: {self.name}: older event ({timetowait})")

                if timetowait < MAXBACKLOGSECS:  # there are things on the queue that don't need to be sent, let's trim:
                    # the item we poped out is older than the queue time, we do not send it
                    logger.debug(f":broadcast: {self.name}: popped old event. Trim other old events..")
                    logger.debug(f":broadcast: {self.name}: {currval[2]} vs now={now} ({timetowait})..")
                    # It's an old event, we don't need to push it back on the queue, we won't send it.
                    self._do_trim()
                    self.rdv = threading.Event() # not really necessary?
                    logger.debug(f":broadcast: {self.name}: ..trim older events completed, restarted listening")

                else:  # we need to send later, let's wait
                    logger.debug(f":broadcast: {self.name}: {pretxt} need to send at {df(currval[2], tz)}, waiting {td(timetowait)}, speed={self.speed}, waiting={round(realtimetowait, 1)}")

                    if not self.rdv.wait(timeout=realtimetowait):
                        # we timed out, we need to send
                        # logger.debug(f":broadcast: {self.name}: sending..")
                        r = self.send_data(currval[1].decode('UTF-8'))
                        if r != 0:
                            logger.warning(f":send_data: did not complete successfully (errcode={r})")
                        currval = None  # currval was sent, we don't need to push it back or anything like that
                        # logger.debug(f":broadcast: {self.name}: ..done")

                    # Now, there is an external event, either reset() or trim() that need us to
                    # temporary stop sending while they do their stuff.
                    else:
                        # First, we were instructed to not send, so we put the popped event back in the queue
                        if currval is not None:
                            logger.debug(f":broadcast: {self.name}: awake, push current event back on queue..")
                            pushback({currval[1]: currval[2]})
                            currval = None
                            logger.debug(f":broadcast: {self.name}: ..done")

                        # May we we were awake to stop...
                        if self.shutdown_flag.is_set():
                            logger.info(f":broadcast: {self.name}: awake to quit, quitting..")
                            continue

                        if self.oktoreset is not None: # Is it a reset() request?
                            logger.info(f":broadcast: {self.name}: awake to reset, resetting..")
                            self.resetcompleted = threading.Event()
                            self.oktoreset.set()
                            logger.debug(f":broadcast: {self.name}: ..waiting reset completes..")
                            self.resetcompleted.wait()
                            # self.rdv = threading.Event()  # done in reset()
                            logger.info(f":broadcast: {self.name}: ..reset completed, restarting")

                        elif self.oktotrim is not None:  # Is it a trim() request?
                            # this is not 100% correct: Some event of nextval array may have already be sent
                            logger.debug(f":broadcast: {self.name}: awake to trim, trimming..")
                            self.trimmingcompleted = threading.Event()
                            self.oktotrim.set()
                            logger.debug(f":broadcast: {self.name}: ..waiting trim completes..")
                            self.trimmingcompleted.wait()
                            # self.rdv = threading.Event()  # done in trim()
                            logger.debug(f":broadcast: {self.name}: ..trim completed, restarting")

                        else:
                            self.rdv = threading.Event()
                            logger.warning(f":broadcast: {self.name}: awaked but don't know why")

        except KeyboardInterrupt:
            logger.warning(f":broadcast: {self.name}: interrupted")
            if currval is not None:
                logger.debug(f":broadcast: {self.name}: keyboard interrupt, push current event back on queue..")
                pushback({currval[1]: currval[2]})
                currval = None
                logger.debug(f":broadcast: {self.name}: ..done")
            else:
                logger.debug(f":broadcast: {self.name}: keyboard interrupt, nothing to push back on queue")
            logger.info(f":broadcast: {self.name}: quitting..")
            self.shutdown_flag.set()
        finally:
            logger.info(f":broadcast: {self.name}: ..bye")



LTlogger = logging.getLogger("LiveTrafficForwarder")

class LiveTrafficForwarder(Broadcaster):

    def __init__(self, redis):
        Broadcaster.__init__(self, redis=redis, name=LIVETRAFFIC_QUEUE)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        LTlogger.debug(f"LiveTrafficForwarder::__init__: inited")

    def send_data(self, data: str) -> int:
        fields = data.split(',')
        if len(fields) != 15:
            LTlogger.warning(f"LiveTrafficForwarder:send_data: Found {len(fields)} fields, expected 15, in line {data}")
            return 1
        # Update and wait for timestamp
        # fields[14] = compWaitTS(fields[14])  # this is done in our own broadcaster :-)
        datagram = ','.join(fields)
        self.sock.sendto(datagram.encode('ascii'), (XPLANE_HOSTNAME, XPLANE_PORT))
        fields[1] = f"{int(fields[1]):x}"
        LTlogger.debug(f"LiveTrafficForwarder::send_data: {datagram}")
        LTlogger.debug(f"LiveTrafficForwarder::send_data: ac:{fields[1]}: alt={fields[4]} ft, hdg={fields[7]}, speed={fields[8]} kn, vspeed={fields[5]} ft/min")
        return 0


# ##############################
# H Y P E R C A S T E R
#
hyperlogger = logging.getLogger("Hypercaster")

class Hypercaster:
    """
    Starts/stop/reset a Broadcaster for each queue.
    Hypercaster is an administrator for all Broadcasters.
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
        hyperlogger.info(f":init: admin_queue started")
        hyperlogger.debug(f":init: {self.queues.keys()}")

    def start_queue(self, queue):
        if self.queues[queue.name].status == RUN:
            b = None
            if queue.name == LIVETRAFFIC_QUEUE:
                if XPLANE_FEED:
                    b = LiveTrafficForwarder(redis.Redis(connection_pool=self.redis_pool))
                    hyperlogger.debug(f":start_queue: LiveTrafficForwarder started")
                else:
                    hyperlogger.debug(f":start_queue: {queue.name} not started")
                    return
            else:
                b = Broadcaster(redis.Redis(connection_pool=self.redis_pool), queue.name, queue.speed, queue.starttime)
            self.queues[queue.name].broadcaster = b
            self.queues[queue.name].thread = threading.Thread(target=b.broadcast)
            self.queues[queue.name].thread.start()
            hyperlogger.info(f":start_queue: {queue.name} started")
        else:
            hyperlogger.warning(f":start_queue: {queue.name} is stopped")

    def terminate_queue(self, queue):
        if hasattr(self.queues[queue], "broadcaster"):
            if hasattr(self.queues[queue].broadcaster, "shutdown_flag"):
                self.queues[queue].broadcaster.shutdown_flag.set()
                hyperlogger.debug(f":terminate_queue: {queue} awakening wait() on send..")
                self.queues[queue].broadcaster.rdv.set()
                # now that we have notified the queue's broadcaster, we don't need it anymore
                self.queues[queue].broadcaster = None
                hyperlogger.debug(f":terminate_queue: {queue} notified")
            else:  # @todo: Why do we sometimes get here??
                hyperlogger.warning(f":terminate_queue: {queue} has no shutdown_flag")  # error?
        else:
            hyperlogger.warning(f":terminate_queue: {queue} has no broadcaster")

    def terminate_all_queues(self):
        hyperlogger.debug(f":terminate_all_queues: notifying..")
        for k in self.queues.keys():
            hyperlogger.debug(f":terminate_all_queues: notifying {k}..")
            self.terminate_queue(k)
        hyperlogger.debug(f":terminate_all_queues: notifying admin..")
        # Trick/convention: We set a queue named QUIT to have the admin_queue to quit
        # Alternative: Set a ADMIN_QUEUE queue/value to some value meaning the action to take.
        self.shutdown_flag.set()
        self.redis.set(QUIT_KEY, QUIT)
        hyperlogger.debug(f":terminate_all_queues: ..done")

    def admin_queue(self):
        # redis events:
        # {'type': 'pmessage', 'pattern': b'__keyspace@0__:*', 'channel': b'__keyspace@0__:queues', 'data': b'del'}
        # {'type': 'pmessage', 'pattern': b'__keyspace@0__:*', 'channel': b'__keyspace@0__:queues:test', 'data': b'del'}

        self.redis.delete(QUIT_KEY)
        pattern = "__key*__:queues:*"
        self.pubsub.psubscribe(pattern)

        hyperlogger.info(":admin_queue: starting..")

        while not self.shutdown_flag.is_set():

            if self.heartbeat: # and last_sent < datetime.now()
                logger.debug(f":admin_queue: listening..")

            message = self.pubsub.get_message(timeout=LISTEN_TIMEOUT)
            if message is not None and type(message) != str and "data" in message:

                # logger.debug(f":admin_queue: analyzing {message}..")

                ty = message["type"]
                if type(ty) == bytes:
                    ty = ty.decode("UTF-8")
                if ty != "pmessage":
                    # logger.debug(f":admin_queue: message type is not pmessage, ignoring")
                    continue

                ty = message["pattern"]
                if type(ty) == bytes:
                    ty = ty.decode("UTF-8")
                if ty != pattern:
                    # logger.debug(f":admin_queue: pattern is not as expected ({ty} vs {pattern}), ignoring")
                    continue

                action = message["data"]
                if type(action) == bytes:
                    action = action.decode("UTF-8")

                if action not in ["set", "del"]:
                    # logger.debug(f":admin_queue: ignoring action {action}")
                    continue

                queuestr = message["channel"]
                if type(queuestr) == bytes:
                    queuestr = queuestr.decode("UTF-8")
                qn = queuestr.split(ID_SEP)[-1]

                logger.debug(f":admin_queue: processing {action} {qn}..")

                # hyperlogger.debug(f":admin_queue: received {msg}")
                if action == "set" and qn == QUIT:
                    hyperlogger.warning(":admin_queue: instructed to quit")
                    hyperlogger.info(":admin_queue: quitting..")
                    self.redis.delete(QUIT_KEY)
                    self.shutdown_flag.set()

                elif action == "set":
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
                            # queue was not working before and does not need to be started
                            hyperlogger.debug(f":admin_queue: ..queue {qn} added/modified but not started")
                        else:
                            # queue was working before, will continue to work but some parameters are reset
                            self.queues[qn].broadcaster = oldbr
                            oldbr.reset(speed=self.queues[qn].speed, starttime=self.queues[qn].starttime)
                            hyperlogger.debug(f":admin_queue: .. queue {qn} speed {self.queues[qn].speed} (was {oldsp}) " +
                                         f"starttime {self.queues[qn].starttime} (was {oldst}) reset")
                        hyperlogger.debug(f":admin_queue: ..done")

                elif action == "del":
                    if qn in self.queues.keys():
                        if not hasattr(self.queues[qn], "deleted"):  # queue already exists, parameter changed, stop it first
                            self.terminate_queue(qn)
                            self.queues[qn].deleted = True
                            hyperlogger.info(f":admin_queue: queue {qn} terminated")
                        else:
                            hyperlogger.debug(f":admin_queue: queue {qn} already deleted")

                else:
                    hyperlogger.warning(f":admin_queue: ignoring '{message}'")

        self.pubsub.unsubscribe(pattern)
        hyperlogger.info(":admin_queue: ..bye")

    def shutdown(self):
        self.terminate_all_queues()
