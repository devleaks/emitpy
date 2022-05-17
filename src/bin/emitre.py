import sys
sys.path.append('/Users/pierre/Developer/oscars/emitpy/src')

import logging

from emitpy.emitapp import EmitApp
from datetime import datetime, timedelta

from emitpy.parameters import MANAGED_AIRPORT

logging.basicConfig(level=logging.DEBUG)

e = EmitApp(MANAGED_AIRPORT)

ret = e.do_schedule(queue="raw",
                    ident="flights:QR095-S201904040610:e",
                    sync="TAKE_OFF",
                    scheduled=(datetime.now() + timedelta(seconds=10)).isoformat(timespec="seconds"))

print(ret)
