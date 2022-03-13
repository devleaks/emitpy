import logging
from rq import Connection, Worker

from service import do_service

with Connection():
    w = Worker(['default'])
    w.work()