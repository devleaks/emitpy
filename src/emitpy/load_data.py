import sys
sys.path.append('/Users/pierre/Developer/oscars/emitpy/src')
import logging

import redis

from emitpy.parameters import REDIS_CONNECT

from emitpy.utils.load_generic import GenericData
from emitpy.utils.load_mngbus import ManagedAirportData
from emitpy.utils.load_mngapt import ManagedAirportFlightData

logging.basicConfig(level=logging.DEBUG)

r = redis.Redis(**REDIS_CONNECT)

g = GenericData(r)
g.load([])
m = ManagedAirportData(r)
m.load(["gse"])
f = ManagedAirportFlightData(r)
f.load([])
