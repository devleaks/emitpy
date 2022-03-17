from datetime import datetime, timedelta
import threading
import time
import redis
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("Broadcaster")


def df(ts):
    return f"{datetime.fromtimestamp(ts).isoformat(timespec='seconds')} ({round(ts, 1)})"

def td(ts):
    return f"{timedelta(seconds=round(ts, 1))} ({round(ts, 1)})"


class Broadcaster:

    def __init__(self, name: str, speed: float = 1, startime: datetime = datetime.now()):
        self.name = name
        self.speed = speed
        self.startime = startime.timestamp()

        self.redis = redis.Redis()
        self.pubsub = self.redis.pubsub()

    def setSpeed(self, speed: float):
        self.speed = speed

    def setStartTime(self, startime: datetime):
        self.startime = startime.timestamp()

    def reset(self):
        self.speed = 1
        self.startime = startime.timestamp()

    def now(self, format: bool = False):
        return datetime.now().timestamp()
        # now = datetime.now().timestamp()
        # diff = now - self.startime
        # compressed = diff / self.speed
        # newnow = self.startime + compressed
        # logger.debug(f"clock: {now}, {diff}, {compressed}: {datetime.fromtimestamp(newnow).isoformat(timespec='seconds')}")
        # return newnow if not format else datetime.fromtimestamp(newnow).isoformat(timespec='seconds')

    def _do_trim(self):
        now = self.now()
        logger.debug(f":_do_trim: {df(now)}): trimming..")
        oldones = self.redis.zrangebyscore(self.name, min=0, max=now)
        if oldones and len(oldones) > 0:
            self.redis.zrem(self.name, *oldones)
            logger.debug(f":_do_trim: ..removed {len(oldones)} messages..done")
        else:
            logger.debug(f":_do_trim: nothing to remove ..done")

    def trim(self):
        self.pubsub.subscribe("Q"+self.name)
        logger.debug(":trim: listening..")
        for message in self.pubsub.listen():
            msg = message["data"]
            if type(msg) == bytes:
                msg = msg.decode('UTF-8')
            logger.debug(f":trim: received {msg}")
            if msg == "new-data":
                logger.debug(":trim: ask sender to stop..")
                # ask run() to stop sending:
                self.oktotrim = threading.Event()
                self.rdv.set()
                logger.debug(":trim: wait sender has stopped..")
                self.oktotrim.wait()
                self._do_trim()
                logger.debug(":trim: tell sender to restart, provide new blocking event..")
                self.trimmingcompleted.set()
                self.rdv = threading.Event()
                logger.debug(":trim: listening again..")
            elif msg == "quit":
                logger.debug(":trim: quitting..")
                return
            else:
                logger.debug(f":trim: ignoring '{msg}'")

    def run(self):
        # "Sender"
        logger.debug(f":run: pre-start trimming..")
        self._do_trim()
        logger.debug(f":run: ..done")
        logger.debug(f":run: starting trimming thread..")
        self.rdv = threading.Event()
        self.trim = threading.Thread(target=self.trim)
        self.trim.start()
        logger.debug(f":run: ..done")

        while True:
            nextval = self.redis.zpopmin(self.name)
            numval = self.redis.zcard(self.name)
            logger.debug(f":run: read {len(nextval)} items, {numval} items left in {self.name} queue")
            # logger.debug(f":run: read {nextval}")
            now = self.now()
            logger.debug(f":run: it is now {df(now)}")
            if len(nextval) > 0:
                for nv in nextval:
                    wt = (nv[1] - now) / self.speed
                    if wt > 0:
                        logger.debug(f":run: need to send at {df(nv[1])}, waiting {td(wt)}")
                        if not self.rdv.wait(timeout=wt):  # we timed out
                            logger.debug(f":run: sending..")
                            logger.debug(nv[0].decode('UTF-8'))
                            logger.debug(f":run: ..done")
                        else:  # we were instructed to not send
                            # put item back in queue
                            logger.debug(f":run: need trimming, push back on queue..")
                            self.redis.zadd(self.name, nextval)
                            # this is not 100% correct: Some event of nextval array may have already be sent
                            # done. ok to trim
                            logger.debug(f":run: ok to trim..")
                            self.oktotrim.set()
                            # wait trimming completed
                            self.trimmingcompleted = threading.Event()
                            logger.debug(f":run: waiting trim completes..")
                            self.trimmingcompleted.wait()
                            logger.debug(f":run: done")
                    else:
                        logger.debug(f":run: should have sent at {df(nv[1])} ({td(wt)})")
                        logger.debug(f":run: did not send {nv[0].decode('UTF-8')}")
        self.trim.join()


    def brun(self):
        # Blocking version of "Sender"
        logger.debug(f":run: pre-start trimming..")
        self._do_trim()
        logger.debug(f":run: ..done")
        logger.debug(f":run: starting trimming thread..")
        self.rdv = threading.Event()
        self.trim = threading.Thread(target=self.trim)
        self.trim.start()
        logger.debug(f":run: ..done")

        try:
            while True:
                logger.debug(f":run: listening..")
                nv = self.redis.bzpopmin(self.name)
                numval = self.redis.zcard(self.name)
                logger.debug(f":run: {numval} items left in {self.name} queue")
                now = self.now()
                logger.debug(f":run: it is now {df(now)}")
                wt = (nv[2] - now) / self.speed
                if wt > 0:
                    logger.debug(f":run: need to send at {df(nv[2])}, waiting {td(wt)}")
                    if not self.rdv.wait(timeout=wt):  # we timed out
                        logger.debug(f":run: sending..")
                        logger.debug(nv[1].decode('UTF-8'))
                        logger.debug(f":run: ..done")
                    else:  # we were instructed to not send
                        # put item back in queue
                        logger.debug(f":run: need trimming, push back on queue..")
                        self.redis.zadd(self.name, {nv[1]: nv[2]})
                        # this is not 100% correct: Some event of nextval array may have already be sent
                        # done. ok to trim
                        logger.debug(f":run: ok to trim..")
                        self.oktotrim.set()
                        # wait trimming completed
                        self.trimmingcompleted = threading.Event()
                        logger.debug(f":run: waiting trim completes..")
                        self.trimmingcompleted.wait()
                        logger.debug(f":run: trim completed, restarted")
                else:
                    logger.debug(f":run: should have sent at {df(nv[2])} ({td(wt)} ago)")
                    logger.debug(f":run: did not send {nv[1].decode('UTF-8')}")
        except KeyboardInterrupt:
            logger.debug(f":run: keyboard interrupt, try to push poped item back on queue..")
            self.redis.zadd(self.name, {nv[1]: nv[2]})
            logger.debug(f":run: ..done")
        finally:
            logger.debug(f":run: quitting..")
            self.redis.publish("Q"+self.name, "quit")
            self.trim.join()
            logger.debug(f":run: ..bye")


b = Broadcaster("adsb")
b.brun()


