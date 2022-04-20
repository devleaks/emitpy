import logging

from emitpy.business import Airline
from emitpy.emit import HyperCaster

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("hypercast")

h = HyperCaster()
h.run()