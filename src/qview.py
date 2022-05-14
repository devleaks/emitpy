"""
Utility script to view outputs of emitpy.
The script listen on all queues.
"""
import redis

redis = redis.Redis(**{
    "host": "localhost",
    "port": 6379,
    "db": 0
})

OUT_QUEUE_PREFIX = "emitpy:"  # could be ""

pubsub = redis.pubsub()
pubsub.psubscribe(OUT_QUEUE_PREFIX+"*")
for message in pubsub.listen():
    print(message)
