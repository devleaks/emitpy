from rq import Connection, Worker
from emitapp import EmitApp

EmitApp.init()

with Connection():
    w = Worker(['default'])
    w.work()