import sys
sys.path.append('/Users/pierre/Developer/oscars/emitpy/src')
import logging

import redis

from emitpy.parameters import REDIS_CONNECT

from emitpy.utils.load_generic import GenericData
from emitpy.utils.load_mngbus import ManagedAirportData
from emitpy.utils.load_mngapt import ManagedAirportFlightData
from emitpy.utils.load_airspc import AirspaceData

logging.basicConfig(level=logging.DEBUG)

r = redis.Redis(**REDIS_CONNECT)

# g = GenericData(r)
# ret = g.load()
# print(ret)
# m = ManagedAirportData(r)
# ret = m.load(["alroute", "alroutefreq"])
# print(ret)
# f = ManagedAirportFlightData(r)
# ret = f.load()
# print(ret)
s = AirspaceData(r)
ret = s.load(["vertex"])
print(ret)
