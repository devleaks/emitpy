import redis
import logging

<<<<<<< HEAD
from ..parameters import REDIS_CONNECT
=======
from emitpy.parameters import REDIS_CONNECT
>>>>>>> 28e09248ea1169b2af9da5ebc0a6af93eb16d385

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("Reader")


class Reader:

    def __init__(self, name: str):
        self.name = name
        self.redis = redis.Redis(**REDIS_CONNECT)
        self.pubsub = self.redis.pubsub()
        self.pubsub.subscribe(self.name)

    def run(self):
        logger.debug(f":run: listening on {self.name}..")
        for message in self.pubsub.listen():
            # logger.debug(f":run: received {message}")
            msg = message["data"]
            if type(msg) == bytes:
                msg = msg.decode('UTF-8')
                self.forward(msg)

    def forward(self, msg):
        # shoud do some check to not forward redis internal messages
        logger.debug(f":forward: {msg}")

<<<<<<< HEAD
r = Reader("lt")
r.run()
=======
r = Reader("raw")
r.run()
>>>>>>> 28e09248ea1169b2af9da5ebc0a6af93eb16d385
