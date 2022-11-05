import sys
sys.path.append('/Users/pierre/Developer/oscars/emitpy/src')

import logging
import random
from datetime import datetime, tzinfo, timedelta

from emitpy.emitapp import EmitApp
from emitpy.aircraft import AircraftPerformance

from emitpy.parameters import MANAGED_AIRPORT
from emitpy.utils import actual_time, Timezone

logging.basicConfig(level=logging.DEBUG)

print(actual_time('2019-04-07T12:55:00+03:00', 'arrival', 10))

heretime = Timezone(offset=2, name="Brussels")
dtactual = datetime.now().replace(tzinfo=heretime)

e = EmitApp(MANAGED_AIRPORT)

ret = e.do_mission(queue="lt",
                   emit_rate=10,
                   operator="HPD",
                   checkpoints=[],
                   mission="security",
                   vehicle_ident="JB007",
                   vehicle_icao24="effaca",
                   vehicle_model="Security",
                   vehicle_startpos="svc:depot:0",
                   vehicle_endpos="svc:depot:4",
                   scheduled=dtactual.isoformat())

print(ret)
