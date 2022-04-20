import sys
import logging

from emitpy.business import Airline
from emitpy.emit import Broadcaster

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("broadcast")

if len(sys.argv) < 2:
    print("usage: python broadcast.py queue_name")
    exit(1)

QUEUE_NAME=sys.argv[1]
b = Broadcaster(QUEUE_NAME)
b.broadcast()
