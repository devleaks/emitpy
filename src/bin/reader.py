import sys
sys.path.append('/Users/pierre/Developer/oscars/emitpy/src')

import redis
import logging
import json

from emitpy.parameters import REDIS_CONNECT


logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("Reader")

format_json = True

class Reader:

    def __init__(self, name: str):
        self.name = name
        try:
            self.redis = redis.Redis(**REDIS_CONNECT)
            self.redis.ping()
        except:
            logger.error(":init: no redis")
            return

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
        try:
            obj = json.loads(msg)
            logger.debug(f":forward: {json.dumps(obj, indent=2)}")
        except ValueError as e:
            logger.debug(f":forward: {msg}")


r = Reader("raw")
r.run()
