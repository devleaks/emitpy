from rq import Connection, Worker
from ex import Ex

Ex.init()

with Connection():
    w = Worker(['default'])
    w.work()