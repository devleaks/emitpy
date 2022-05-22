import sys
sys.path.append('/Users/pierre/Developer/oscars/emitpy/src')

import logging

from emitpy.emitapp import EmitApp
from datetime import datetime, timedelta

from emitpy.parameters import MANAGED_AIRPORT

logging.basicConfig(level=logging.DEBUG)

e = EmitApp(MANAGED_AIRPORT)

ret = e.do_schedule(queue="raw",
                    ident="services:FuelService:E17R:2019-04-05T02.50.00+03.00:FUEPU000:e",
                    sync="start",
                    scheduled=(datetime.now() + timedelta(seconds=10)).isoformat(timespec="seconds"))

print(ret)
