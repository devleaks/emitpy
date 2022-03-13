from rq import Queue
from redis import Redis
import time
from service import do_service
# Tell RQ what Redis connection to use
redis_conn = Redis()
q = Queue(connection=redis_conn)  # no args implies the default queue

# Delay execution of count_words_at_url('http://nvie.com')
job = q.enqueue(do_service, "MATAR", "Fuel", 24, "510", "A321", "FUE51", "aabbcc", "pump", "depot", "depot", "2022-03-13T14:48:00+02:00")
print(job.result)   # => None

# Now, wait a while, until the worker is finished
time.sleep(10)
print(job.result)