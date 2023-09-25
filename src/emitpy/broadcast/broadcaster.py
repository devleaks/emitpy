#
import logging
from datetime import datetime, timedelta
import threading
import socket
import redis
from termcolor import colored

from emitpy.constants import (
    ID_SEP,
    LIVETRAFFIC_QUEUE,
    PUBSUB_CHANNEL_PREFIX,
    LIVETRAFFIC_VERBOSE,
)
from emitpy.parameters import (
    REDIS_CONNECT,
    BROADCASTER_HEARTBEAT,
    BROADCASTER_VERBOSE,
    BROADCASTER_TICK,
)
from emitpy.parameters import XPLANE_FEED, XPLANE_HOSTNAME, XPLANE_PORT

from .queue import Queue, RUN, STOP, QUIT

QUIT_KEY = Queue.mkDataKey(QUIT)

logger = logging.getLogger("Broadcaster")


# Utility functions for debugging time and printing timestamp nicely
def df(ts, tz=None):
    return f"{datetime.fromtimestamp(ts).astimezone(tz=tz).isoformat(timespec='seconds')} (ts={round(ts, 1)})"


def td(ts):
    return f"{timedelta(seconds=round(ts))} ({round(ts, 1)})"


QUEUE_COLORS = {"wire": "yellow"}


# ##############################
# C O N F I G
#
# Delicate parameters, too dangerous to externalize
#
ZPOPMIN_TIMEOUT = 5.0  # secs
LISTEN_TIMEOUT = 5.0
PING_FREQUENCY = 10.0  # once every PING_FREQUENCY * ZPOPMIN_TIMEOUT seconds

# MAXBACKLOGSECS is the maximum negative time we tolerate
# for sending events late (in seconds)
MAXBACKLOGSECS = -20  # 0 is too critical, but MUST be <=0


# ##############################
# B R O A D C A S T E R
#
class Broadcaster:
    """
    The Broadcaster is the executor of a :py:class:`emitpy.broadcast.queue.Queue`.
    It pops items from the sorted set, reads the timestamp,
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
        # logger.debug(f"{self.name}: start_time: {self._starttime}, speed: {self.speed}")
        self.timeshift = None
        self.total_sent = 0

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
        """
        Compute time difference (time shift) at time of call.
        """
        self.timeshift = datetime.now().astimezone() - self.starttime()  # timedelta
        if self.timeshift < timedelta(seconds=10):
            self.timeshift = timedelta(seconds=0)
        logger.debug(
            f"{self.name}: timeshift: {self.timeshift}, now: {df(datetime.now().timestamp())}, queue time: {df(self.now())}"
        )
        return self.timeshift

    def starttime(self):
        """
        Returns this broadcaster' start time.
        """
        if self._starttime is None:
            return datetime.now().astimezone()  # should never happen...
        return self._starttime

    def getInfo(self):
        """
        Get Broadcaster information string.
        """
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
            "queue-time": self.now(format_output=True),
        }

    def reset(self, speed: float = 1, starttime: datetime = None):
        """
        Resets the Broadcaster. Restart at start_time and flows at speed.

        :param      speed:      The speed
        :type       speed:      float
        :param      starttime:  The starttime
        :type       starttime:  datetime
        """
        # We need to ask the broadcaster to stop, put poped item back in queue
        logger.debug(f"prepare..")
        self.oktoreset = threading.Event()
        logger.debug(f"..ready. wake up broadcaster..")
        self.rdv.set()
        logger.debug(f"..wait for broadcaster to block..")
        self.oktoreset.wait()
        self.oktoreset = None
        logger.debug(f"..freed, resetting..")
        ## _do_reset():
        self.speed = speed
        if starttime is not None:
            if type(starttime) == str:
                self._starttime = datetime.fromisoformat(starttime)
            else:
                self._starttime = starttime
            self.setTimeshift()
        ##
        logger.debug(f"..reset, tell broadcaster to restart..")
        self.rdv = threading.Event()
        self.resetcompleted.set()
        logger.debug(f"..cleaned, done")

    def now(self, format_output: bool = False, verbose: bool = False):
        """
        Returns the Broadcaster's "now" time, taking into account its start time and flow speed.

        :param      format_output:  The format output
        :type       format_output:  bool
        :param      verbose:        The verbose
        :type       verbose:        bool
        """
        realnow = datetime.now().astimezone()
        if self.speed == 1 and self.timeshift.total_seconds() == 0:
            newnow = realnow
            if verbose:
                logger.debug(
                    f"{self.name}: no time speed, no time shift: new now: {df(newnow.timestamp())}"
                )
            return (
                newnow.timestamp()
                if not format_output
                else newnow.isoformat(timespec="seconds")
            )

        if verbose:
            logger.debug(f"{self.name}: asked at {df(realnow.timestamp())})")
        elapsed = realnow - (
            self.starttime() + self.timeshift
        )  # time elapsed since setTimeshift().
        if verbose:
            logger.debug(f"{self.name}: real elapsed since start of queue: {elapsed})")
        if self.speed == 1:
            newnow = self.starttime() + elapsed
            if verbose:
                logger.debug(
                    f"{self.name}: no time speed: new now: {df(newnow.timestamp())}"
                )
        else:
            newdeltasec = elapsed.total_seconds() * self.speed
            newdelta = timedelta(seconds=newdeltasec)
            newnow = self.starttime() + newdelta
            if verbose:
                logger.debug(
                    f"{self.name}: time speed {self.speed}: new elapsed: {newdelta}, new now={df(newnow.timestamp())}"
                )
        return (
            newnow.timestamp()
            if not format_output
            else newnow.isoformat(timespec="seconds")
        )

    def _do_trim(self, ident=None):
        """
        Removes elements in sorted set that are outdated for this queue's time.
        """
        now = self.now()
        queue_key = Queue.mkDataKey(self.name)
        msg = "" if ident is None else f"{ident}:"
        logger.debug(f"{self.name}:{msg} {df(now)}: trimming..")
        oldones = self.redis.zrangebyscore(queue_key, min=0, max=now)
        if oldones and len(oldones) > 0:
            self.redis.zrem(queue_key, *oldones)
            logger.debug(f"{self.name}: ..removed {len(oldones)} messages..done")
        else:
            logger.debug(f"{self.name}: ..nothing to remove ..done")

    def trim(self):
        """
        Wrapper to prevent new "pop" while trimming the queue.
        If new elements are added while, it does not matter because
        they will be trimmed at the end of their insertion.
        """
        queue_key = Queue.mkDataKey(self.name)
        pattern = "__keyspace@0__:" + queue_key
        self.pubsub.subscribe(pattern)

        logger.info(f"{self.name}: trim starting..")

        while not self.shutdown_flag.is_set():
            if self.heartbeat:
                logger.debug(
                    f"{self.name}: queue time: {self.now(format_output=True)} listening.."
                )

            # logger.debug(f"{self.name}: waiting for message (with timeout {LISTEN_TIMEOUT} secs.)..")
            # "pmessage","__key*__:*","__keyspace@0__:test","zadd"
            message = self.pubsub.get_message(timeout=LISTEN_TIMEOUT)
            if message is not None and type(message) != str and "data" in message:
                # logger.debug(f"analyzing {message}..")

                ty = message["type"]
                if type(ty) == bytes:
                    ty = ty.decode("UTF-8")
                if ty != "message":
                    # logger.debug(f"message type is not pmessage, ignoring")
                    continue

                ty = message["pattern"]
                if type(ty) == bytes:
                    ty = ty.decode("UTF-8")
                if ty != None:
                    logger.warning(
                        f"pattern is not as expected ({ty} vs {pattern}), ignoring"
                    )
                    continue

                action = message["data"]
                if type(action) == bytes:
                    action = action.decode("UTF-8")

                if action not in ["zadd"]:
                    # logger.debug(f"ignoring action {action}")
                    continue

                queuestr = message["channel"]
                if type(queuestr) == bytes:
                    queuestr = queuestr.decode("UTF-8")
                qn = queuestr.split(ID_SEP)[-1]

                logger.debug(f"processing {action} {qn}..")

                if action == "zadd":
                    logger.debug(f"{self.name}: ask sender to stop..")
                    # ask run() to stop sending:
                    self.oktotrim = threading.Event()
                    self.rdv.set()
                    logger.debug(f"{self.name}: wait sender has stopped..")
                    self.oktotrim.wait()
                    self.oktotrim = None
                    self._do_trim(ident="zadd")
                    logger.debug(
                        f"{self.name}: tell sender to restart, provide new blocking event.."
                    )
                    self.rdv = threading.Event()
                    self.trimmingcompleted.set()
                    logger.info(f"{self.name}: listening again..")

                else:
                    logger.debug(f"{self.name}: ignoring '{msg}'")

        self.pubsub.unsubscribe(pattern)
        logger.info(f"{self.name}: ..trim bye")

    def send_data(self, data: str) -> int:
        """
        Sends data on Redis Publish/Subscribe for this queue.

        :param      data:  The data
        :type       data:  str

        :returns:   { description_of_the_return_value }
        :rtype:     int
        """
        # l = min(30, len(data))
        # logger.debug(f"'{data[0:l]}'...")
        self.redis.publish(PUBSUB_CHANNEL_PREFIX + self.name, data)
        self.total_sent = self.total_sent + 1
        return 0

    def broadcast(self):
        """
        Pop elements from the sorted set at requested time and publish it on pub/sub queue.
        """

        def pushback(item):
            if item is not None:
                # Trick to NOT zadd on self.name: We add one another key, then merge keys.
                queue_key = Queue.mkDataKey(self.name)
                temporary_key = queue_key + "-TMP"
                oset = self.redis.pipeline()
                oset.zadd(temporary_key, item)
                oset.zunionstore(queue_key, [queue_key, temporary_key])
                oset.delete(temporary_key)
                ret = oset.execute()
                logger.debug(f"{self.name}: last item pushed back")
                # self.redis.zadd(self.name, {currval[1]: currval[2]})

        maxbocklog = MAXBACKLOGSECS
        if maxbocklog > 0:
            maxbocklog = -maxbocklog  # MUST be <=0 I said

        queue_key = Queue.mkDataKey(self.name)

        tz = self._starttime.tzinfo if hasattr(self._starttime, "tzinfo") else None

        logger.debug(f"{self.name}: pre-start trimming..")
        self._do_trim("init")
        logger.debug(f"{self.name}: ..done")
        logger.debug(f"{self.name}: starting trimming thread..")
        self.rdv = threading.Event()
        self.shutdown_flag = threading.Event()
        self.trim_thread = threading.Thread(target=self.trim)
        self.trim_thread.start()
        logger.debug(f"{self.name}: ..done")

        currval = None
        ping = 0
        last_sent = datetime.now() - timedelta(seconds=1)

        logger.info(f"{self.name}: broadcast starting..")

        # Wrapped in a big try:/except: to catch errors and keyboard interrupts.
        try:
            while not self.shutdown_flag.is_set():
                dummy = self.now(format_output=True)

                if self.oktotrim is not None:
                    if not self.oktotrim.is_set():
                        logger.warning(f"{self.name}: trimmer is waiting, releasing..")
                        self.trimmingcompleted = threading.Event()
                        self.oktotrim.set()
                        logger.warning(f"{self.name}: ..waiting trim completes..")
                        self.trimmingcompleted.wait()
                        # self.rdv = threading.Event()  # done in trim()
                        logger.warning(f"{self.name}: ..trim completed, restarting")
                        continue
                    else:
                        logger.error(f"{self.name}: trimmer is waiting but not set")

                currval = self.redis.bzpopmin(queue_key, timeout=ZPOPMIN_TIMEOUT)

                if currval is None:
                    # we may have some reset work to do
                    if self.oktoreset is not None:  # Is it a reset() request?
                        logger.info(
                            f"{self.name}: bzpop timed out, reset requested. resetting.."
                        )
                        self.resetcompleted = threading.Event()
                        self.oktoreset.set()
                        logger.debug(f"{self.name}: ..waiting reset completes..")
                        self.resetcompleted.wait()
                        # self.rdv = threading.Event()  # done in reset()
                        logger.info(f"{self.name}: ..reset completed, restarting")
                    else:
                        if self.heartbeat:  # and last_sent < datetime.now()
                            logger.debug(
                                f"{self.name}: nothing to send, bzpopmin timed out.."
                            )
                    continue

                numval = self.redis.zcard(queue_key)
                # logger.debug(f"{self.name}: {numval} items left in queue")
                pretxt = f"{numval} items left in queue,"
                now = self.now()
                # logger.debug(f"{self.name}: it is now {df(now)}")
                # logger.debug(f"{self.name}: at {df(now)}: {numval} in queue")
                timetowait = currval[2] - now  # wait time independant of time warp
                realtimetowait = (
                    timetowait / self.speed
                )  # real wait time, taking warp time into account

                if timetowait < 0:
                    # there is a thing on top that should have be sent earlier
                    # me be we were busy doing something else, and just need to catchup.
                    # Example: 2 events just a few millisecs apart
                    logger.debug(f"{self.name}: older event ({timetowait})")

                if (
                    timetowait < maxbocklog
                ):  # there are things on the queue that don't need to be sent, let's trim:
                    # the item we poped out is older than the queue time, we do not send it
                    logger.debug(
                        f"{self.name}: popped old event. Trim other old events.."
                    )
                    logger.debug(
                        f"{self.name}: {currval[2]} vs now={now} ({timetowait}).."
                    )
                    # It's an old event, we don't need to push it back on the queue, we won't send it.
                    self._do_trim("older")
                    self.rdv = threading.Event()  # not really necessary?
                    logger.debug(
                        f"{self.name}: ..trim older events completed, restarted listening"
                    )

                else:  # we need to send later, let's wait
                    if BROADCASTER_VERBOSE or self.total_sent % BROADCASTER_TICK == 0:
                        txt = f"{self.name}: {pretxt} need to send at {df(currval[2], tz)}, waiting {td(timetowait)}, speed={self.speed}, waiting={round(realtimetowait, 1)}"
                        if self.name in QUEUE_COLORS.keys():
                            logger.debug(colored(txt, QUEUE_COLORS[self.name]))
                        else:
                            logger.debug(txt)

                    if not self.rdv.wait(timeout=realtimetowait):
                        # we timed out, we need to send
                        # logger.debug(f"{self.name}: sending..")
                        r = self.send_data(currval[1].decode("UTF-8"))
                        if r != 0:
                            logger.warning(
                                f"did not complete successfully (errcode={r})"
                            )
                        currval = None  # currval was sent, we don't need to push it back or anything like that
                        # logger.debug(f"{self.name}: ..done")

                    # Now, there is an external event, either reset() or trim() that need us to
                    # temporary stop sending while they do their stuff.
                    else:
                        # First, we were instructed to not send, so we put the popped event back in the queue
                        if currval is not None:
                            logger.debug(
                                f"{self.name}: awake, push current event back on queue.."
                            )
                            pushback({currval[1]: currval[2]})
                            currval = None
                            logger.debug(f"{self.name}: ..done")

                        # May we we were awake to stop...
                        if self.shutdown_flag.is_set():
                            logger.info(f"{self.name}: awake to quit, quitting..")
                            continue

                        if self.oktoreset is not None:  # Is it a reset() request?
                            logger.info(f"{self.name}: awake to reset, resetting..")
                            self.resetcompleted = threading.Event()
                            self.oktoreset.set()
                            logger.debug(f"{self.name}: ..waiting reset completes..")
                            self.resetcompleted.wait()
                            # self.rdv = threading.Event()  # done in reset()
                            logger.info(f"{self.name}: ..reset completed, restarting")

                        elif self.oktotrim is not None:  # Is it a trim() request?
                            # this is not 100% correct: Some event of nextval array may have already be sent
                            logger.debug(f"{self.name}: awake to trim, trimming..")
                            self.trimmingcompleted = threading.Event()
                            self.oktotrim.set()
                            logger.debug(f"{self.name}: ..waiting trim completes..")
                            self.trimmingcompleted.wait()
                            # self.rdv = threading.Event()  # done in trim()
                            logger.debug(f"{self.name}: ..trim completed, restarting")

                        else:
                            self.rdv = threading.Event()
                            logger.warning(f"{self.name}: awaked but don't know why")

        except KeyboardInterrupt:
            logger.warning(f"{self.name}: interrupted")
            if currval is not None:
                logger.debug(
                    f"{self.name}: keyboard interrupt, push current event back on queue.."
                )
                pushback({currval[1]: currval[2]})
                currval = None
                logger.debug(f"{self.name}: ..done")
            else:
                logger.debug(
                    f"{self.name}: keyboard interrupt, nothing to push back on queue"
                )
            logger.info(f"{self.name}: quitting..")
            self.shutdown_flag.set()
        finally:
            logger.info(f"{self.name}: ..sent {self.total_sent} messages..")
            logger.info(f"{self.name}: ..broadcast bye")


LTlogger = logging.getLogger("LiveTrafficForwarder")


class LiveTrafficForwarder(Broadcaster):
    """
    LiveTrafficForwarder is a special Broadcaster that dequeues messages
    and forwards them to a TCP or UDP or multicast port for the LiveTraffic plugin
    in the X-Plane flight simulator game.
    """

    def __init__(self, redis):
        Broadcaster.__init__(self, redis=redis, name=LIVETRAFFIC_QUEUE)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)  # UDP
        # self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)  # Multicast
        # self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 8)
        LTlogger.debug(f"LiveTrafficForwarder::__init__: inited")

    def send_data_lt(self, data: str) -> int:
        """
        Send data to LiveTraffic.
        Send a UDP datagram to a port supplied in parameter file.
        (alternative experimental version.)

        :param      data:  The data
        :type       data:  str

        :returns:   { description_of_the_return_value }
        :rtype:     int
        """
        fields = data.split(",")
        if len(fields) != 15:
            LTlogger.warning(
                f"LiveTrafficForwarder:send_data_lt: Found {len(fields)} fields, expected 15, in line {data}"
            )
            return 1
        # Update and wait for timestamp
        # fields[14] = compWaitTS(fields[14])  # this is done in our own broadcaster :-)
        datagram = ",".join(fields)
        self.sock.sendto(datagram.encode("ascii"), (XPLANE_HOSTNAME, XPLANE_PORT))
        fields[1] = f"{int(fields[1]):x}"
        LTlogger.debug(f"LiveTrafficForwarder::send_data_lt: {datagram}")
        LTlogger.debug(
            f"LiveTrafficForwarder::send_data_lt: ac:{fields[1]}: alt={fields[4]} ft, hdg={fields[7]}, speed={fields[8]} kn, vspeed={fields[5]} ft/min"
        )
        return 0

    def send_data(self, data: str) -> int:
        """
        Send data to LiveTraffic.
        Send a UDP datagram to a port supplied in parameter file.

        :param      data:  The data
        :type       data:  str

        :returns:   { description_of_the_return_value }
        :rtype:     int
        """
        datagram = data
        self.sock.sendto(datagram.encode("ascii"), (XPLANE_HOSTNAME, XPLANE_PORT))
        if LIVETRAFFIC_VERBOSE:
            LTlogger.debug(
                f"LiveTrafficForwarder::send_data({XPLANE_HOSTNAME}:{XPLANE_PORT}):\n{datagram}"
            )
        return 0


# ##############################
# H Y P E R C A S T E R
#
hyperlogger = logging.getLogger("Hypercaster")


class Hypercaster:
    """
    The Hypercaster is a manager of Broadcasters.
    It starts, pause, reset, ends broadcasters gracefuly.
    """

    _instance = None
    _lock = threading.Lock()

    @classmethod
    def __new__(cls, *args, **kwargs):
        """
        Thread safe Hypercaster singleton instanciation

        :param      cls:     The cls
        :type       cls:     { type_description }
        :param      args:    The arguments
        :type       args:    list
        :param      kwargs:  The keywords arguments
        :type       kwargs:  dictionary
        """

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
        hyperlogger.info(f"started {list(self.queues.keys())} and admin queue")

    def init(self):
        """
        Initializes the Hypercaster.
        On startup, create all existing queue Broadcasters
        """
        self.queues = Queue.loadAllQueuesFromDB(self.redis)
        for k in self.queues.values():
            self.start_queue(k)
        self.admin_queue_thread = threading.Thread(target=self.admin_queue)
        self.admin_queue_thread.start()
        hyperlogger.info(f"admin_queue started")

    def start_queue(self, queue):
        """
        Starts a queue Broadcaster.

        :param      queue:  The queue
        :type       queue:  { type_description }
        """
        if self.queues[queue.name].status == RUN:
            b = None
            if queue.name == LIVETRAFFIC_QUEUE:
                if XPLANE_FEED:
                    b = LiveTrafficForwarder(
                        redis.Redis(connection_pool=self.redis_pool)
                    )
                    hyperlogger.debug(f"LiveTrafficForwarder started")
                else:
                    hyperlogger.debug(f"{queue.name} not started")
                    return
            else:
                b = Broadcaster(
                    redis.Redis(connection_pool=self.redis_pool),
                    queue.name,
                    queue.speed,
                    queue.starttime,
                )
            self.queues[queue.name].broadcaster = b
            self.queues[queue.name].thread = threading.Thread(target=b.broadcast)
            self.queues[queue.name].thread.start()
            hyperlogger.info(f"{queue.name} started")
        else:
            hyperlogger.warning(f"{queue.name} is stopped")

    def terminate_queue(self, queue):
        """
        Gracefully terminates the named queue Broadcaster.

        :param      queue:  The queue
        :type       queue:  { type_description }
        """
        if hasattr(self.queues[queue], "deleted"):
            if self.queues[queue].deleted:
                hyperlogger.debug(f"{queue} has already been deleted, do nothing")
                return
        if hasattr(self.queues[queue], "broadcaster"):
            if (
                hasattr(self.queues[queue].broadcaster, "shutdown_flag")
                and self.queues[queue].broadcaster.shutdown_flag is not None
            ):
                self.queues[queue].broadcaster.shutdown_flag.set()
                hyperlogger.debug(f"{queue} awakening wait() on send..")
                if (
                    hasattr(self.queues[queue].broadcaster, "rdv")
                    and self.queues[queue].broadcaster.rdv is not None
                ):
                    self.queues[queue].broadcaster.rdv.set()
                else:
                    hyperlogger.warning(f"{queue} has no rdv")  # error?
                # now that we have notified the queue's broadcaster, we don't need it anymore
                self.queues[queue].broadcaster = None
                hyperlogger.debug(f"{queue} notified")
            else:  # @todo: Why do we sometimes get here??
                hyperlogger.warning(f"{queue} has no shutdown_flag")  # error?
        else:
            hyperlogger.warning(f"{queue} has no broadcaster")

    def terminate_all_queues(self):
        """
        Gracefully terminates all individual Broadcaster, their threads, etc.
        """
        hyperlogger.debug(f"notifying..")
        for k in self.queues.keys():
            hyperlogger.debug(f"notifying {k}..")
            self.terminate_queue(k)
        hyperlogger.debug(f"notifying admin..")
        # Trick/convention: We set a queue named QUIT to have the admin_queue to quit.
        # This provoke a Redis keyspace notification that we capture to terminate the admin queue.
        # Alternative: Set a ADMIN_QUEUE queue/value to some value meaning the action to take.
        self.shutdown_flag.set()
        self.redis.set(QUIT_KEY, QUIT)
        hyperlogger.debug(f"..done")

    def admin_queue(self):
        """
        Reads message on the Redis interal admin queue to detect queue create or suppression.
        Starts or stops a Broadcaster accordingly.
        """

        # redis events:
        # {'type': 'pmessage', 'pattern': b'__keyspace@0__:*', 'channel': b'__keyspace@0__:queues', 'data': b'del'}
        # {'type': 'pmessage', 'pattern': b'__keyspace@0__:*', 'channel': b'__keyspace@0__:queues:test', 'data': b'del'}

        self.redis.delete(QUIT_KEY)
        pattern = "__key*__:queues:*"
        self.pubsub.psubscribe(pattern)

        hyperlogger.info("admin starting..")

        while not self.shutdown_flag.is_set():
            if self.heartbeat:  # and last_sent < datetime.now()
                logger.debug(f"listening..")

            message = self.pubsub.get_message(timeout=LISTEN_TIMEOUT)
            if message is not None and type(message) != str and "data" in message:
                # logger.debug(f"analyzing {message}..")

                ty = message["type"]
                if type(ty) == bytes:
                    ty = ty.decode("UTF-8")
                if ty != "pmessage":
                    # hyperlogger.debug(f"message type is not pmessage, ignoring")
                    continue

                ty = message["pattern"]
                if type(ty) == bytes:
                    ty = ty.decode("UTF-8")
                if ty != pattern:
                    # hyperlogger.debug(f"pattern is not as expected ({ty} vs {pattern}), ignoring")
                    continue

                action = message["data"]
                if type(action) == bytes:
                    action = action.decode("UTF-8")

                if action not in ["set", "del"]:
                    # hyperlogger.debug(f"ignoring action {action}")
                    continue

                queuestr = message["channel"]
                if type(queuestr) == bytes:
                    queuestr = queuestr.decode("UTF-8")
                qn = queuestr.split(ID_SEP)[-1]

                # logger.debug(f"processing {action} {qn}..")

                # hyperlogger.debug(f"received {msg}")
                if (
                    action == "set" and qn == QUIT
                ):  # this was provoked by self.redis.set(QUIT_KEY, QUIT)
                    hyperlogger.warning("instructed to quit")
                    hyperlogger.info("quitting..")
                    self.redis.delete(QUIT_KEY)
                    self.shutdown_flag.set()

                elif action == "set":
                    if qn not in self.queues.keys():
                        self.queues[qn] = Queue.loadFromDB(name=qn, redis=self.redis)
                        self.start_queue(self.queues[qn])
                    elif hasattr(self.queues[qn], "deleted"):
                        if self.queues[qn].deleted:
                            hyperlogger.info(f"queue {qn} was deleted, restarting..")
                            self.queues[qn] = Queue.loadFromDB(
                                name=qn, redis=self.redis
                            )
                            self.start_queue(self.queues[qn])
                            self.queues[
                                qn
                            ].broadcaster.rdv = threading.Event()  # oulalaaaa!?
                    else:  # queue already exists, parameter changed, stop it first
                        hyperlogger.debug(f"queue {qn} already running, reseting..")
                        oldsp = self.queues[qn].speed
                        oldst = self.queues[qn].starttime
                        # there is no broadcaster if queue was not started
                        oldbr = (
                            self.queues[qn].broadcaster
                            if hasattr(self.queues[qn], "broadcaster")
                            else None
                        )
                        # if oldbr is None:
                        #     hyperlogger.debug(f"..queue {qn} had no broadcaster..")
                        # else:
                        #     hyperlogger.debug(f"..queue reusing {qn} broadcaster..")
                        self.queues[qn] = Queue.loadFromDB(redis=self.redis, name=qn)
                        if oldbr is not None and self.queues[qn].status == STOP:
                            # queue was working beofre and is now stopped: replaces broadcaster and terminates it
                            self.queues[qn].broadcaster = oldbr
                            self.terminate_queue(qn)
                            hyperlogger.debug(f"..queue {qn} stopped")
                        elif oldbr is None and self.queues[qn].status == RUN:
                            # queue was not working before and is now started
                            self.start_queue(self.queues[qn])
                            hyperlogger.debug(f"..queue {qn} started")
                        elif oldbr is None and self.queues[qn].status == STOP:
                            # queue was not working before and does not need to be started
                            hyperlogger.debug(
                                f"..queue {qn} added/modified but not started"
                            )
                        else:
                            # queue was working before, will continue to work but some parameters are reset
                            self.queues[qn].broadcaster = oldbr
                            oldbr.reset(
                                speed=self.queues[qn].speed,
                                starttime=self.queues[qn].starttime,
                            )
                            hyperlogger.debug(
                                f"..queue {qn} speed {self.queues[qn].speed} (was {oldsp}) "
                                + f"starttime {self.queues[qn].starttime} (was {oldst}) reset"
                            )
                        hyperlogger.debug(f"..done")

                elif action == "del":
                    # we want to delete a queue when queues:<queue_name> key is deleted.
                    # we do NOT delete the queue if queues:data:<queue_name>, which contains emissions, is deleted
                    # queues:data:<queue_name> is deleted when we remove the last emission from it (when it is empty)
                    # 'channel': b'__keyspace@0__:queues:test' => delete test queue, we terminate it.
                    # 'channel': b'__keyspace@0__:queues:data:test' => delete test data queue but we ignore it (just report debug)
                    if not ":data:" in queuestr:
                        if qn in self.queues.keys():
                            # hyperlogger.info(f"queue {qn} vars: {vars(self.queues[qn])}")
                            if not hasattr(
                                self.queues[qn], "deleted"
                            ):  # queue already exists, parameter changed, stop it first
                                self.terminate_queue(qn)
                                self.queues[qn].deleted = True
                                hyperlogger.info(f"queue {qn} terminated")
                            else:
                                hyperlogger.debug(f"queue {qn} already deleted")
                    else:
                        hyperlogger.debug(f"queue {qn} has no more data")

                else:
                    hyperlogger.warning(f"ignoring '{message}'")

        self.pubsub.unsubscribe(pattern)
        self.redis.delete(QUIT_KEY)
        hyperlogger.info("..admin bye")

    def shutdown(self):
        """
        Shut down all broadcasters. Shutdown Hypercaster.
        """
        self.terminate_all_queues()
