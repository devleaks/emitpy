from emitpy.emitapp import EmitApp
from datetime import datetime, timedelta

from emitpy.parameters import MANAGED_AIRPORT

e = EmitApp(MANAGED_AIRPORT)

ret = e.do_schedule(ident="FuelService-FUE001-A7", sync="service-start", scheduled=(datetime.now() + timedelta(seconds=10)).isoformat(timespec="seconds"))
print(ret)
