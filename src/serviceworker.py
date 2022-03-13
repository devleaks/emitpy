from rq import Connection, Worker
from serviceexec import DoService

DoService.init()

with Connection():
    w = Worker(['default'])
    w.work()