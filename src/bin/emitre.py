import sys
sys.path.append('/Users/pierre/Developer/oscars/emitpy/src')

import logging

from emitpy.emitapp import EmitApp
from datetime import datetime, timedelta

from emitpy.parameters import MANAGED_AIRPORT

logging.basicConfig(level=logging.DEBUG)

e = EmitApp(MANAGED_AIRPORT)

ret = e.do_schedule(queue="raw",
                    ident="flights:QR1139-S201904031320:e",
                    sync="ONBLOCK",
                    scheduled=(datetime.now() + timedelta(seconds=10)).isoformat(),
                    do_services=True)

print(ret)
