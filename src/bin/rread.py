import sys
sys.path.append('/Users/pierre/Developer/oscars/emitpy/src')

import redis

from emitpy.parameters import REDIS_CONNECT


name="__keyspace@0__:*"
redis = redis.Redis(**REDIS_CONNECT)
pubsub = redis.pubsub()
pubsub.psubscribe(name)

print(f":run: listening on {name}..")
for message in pubsub.listen():
    print(f":run: received {message}")
