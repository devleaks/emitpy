import time

from rq import Queue
from redis import Redis

from serviceexec import DoService


# Tell RQ what Redis connection to use
redis_conn = Redis()
q = Queue(connection=redis_conn)  # no args implies the default queue

# Delay execution of count_words_at_url('http://nvie.com')
job = q.enqueue(DoService.do_flight, "QR", "1", "2022-03-13T14:48:00+02:00", "SYZ", "arrival", "A320", "A7", "abcabc", "A7-PMA", "RW16L")
print(job.result)   # => None

# Now, wait a while, until the worker is finished
time.sleep(10)
print(job.result)