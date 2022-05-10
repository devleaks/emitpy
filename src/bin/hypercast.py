import logging

from emitpy.business import Airline
from emitpy.emit import Hypercaster

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("hypercast")

h = Hypercaster()
h.run()