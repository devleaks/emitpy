from datetime import datetime
import threading
import time
import redis

class Broadcaster:

    def __init__(self, name: str, speed: float = 1, startime: datetime = datetime.now()):
        self.name = name
        self.speed = speed
        self.startime = startime.timestamp()

        self.redis = redis.Redis()
        self.pubsub = self.redis.pubsub()
        self.trim = threading.Thread(target=self.trim)

        self.trim.start()

    def setSpeed(self, speed: float):
        self.speed = speed

    def setStartTime(self, startime: datetime):
        self.startime = startime.timestamp()

    def now(self, format: bool = False):
        now = datetime.now().timestamp()
        diff = now - self.startime
        compressed = diff / self.speed
        newnow = self.startime + compressed
        print(f"clock: {now}, {diff}, {compressed}: {datetime.fromtimestamp(newnow).isoformat(timespec='seconds')}")
        return newnow if not format else datetime.fromtimestamp(newnow).isoformat(timespec='seconds')

    def reset(self):
        self.speed = 1
        self.startime = startime.timestamp()

    def _do_trim(self):
        now = self.now()
        print(f"it is now {now} ({self.now(True)}): trimming..")
        oldones = self.redis.zrangebyscore(self.name, min=0, max=now)
        if oldones and len(oldones) > 0:
            self.redis.zrem(self.name, *oldones)
            print(f"..removed {len(oldones)} messages..done")
        else:
            print(f"nothing to remove ..done")

    def trim(self):
        self.pubsub.subscribe("Q"+self.name)
        print("listening...")
        for msg in self.pubsub.listen():
            print(msg["data"])
            self._do_trim()

    def run(self):
        self._do_trim()
        while True:
            nextval = self.redis.zpopmin(self.name, 10)
            now = self.now()
            print(f"it is now {now} ({self.now(True)})")
            if len(nextval) > 0:
                for nv in nextval:
                    wt = (nv[1] - now) / self.speed
                    if wt > 0:
                        print(f"should send at {nv[1]} ({datetime.fromtimestamp(nv[1]).isoformat(timespec='seconds')}), waiting {wt}")
                        time.sleep(wt)
                        print(nv[0].decode('UTF-8'))
                    else:
                        print(f"should have sent earlier {wt}")
                        print(nv[0].decode('UTF-8'))
        self.trim.join()

b = Broadcaster("adsb")
b.run()