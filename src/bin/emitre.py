from emitpy.emitapp import EmitApp
from datetime import datetime, timedelta

from emitpy.parameters import MANAGED_AIRPORT

e = EmitApp(MANAGED_AIRPORT)

ret = e.do_schedule(queue="raw",
                    ident="FuelService:H3:FUE003",
                    sync="service-start",
                    scheduled=(datetime.now() + timedelta(seconds=10)).isoformat(timespec="seconds"))
print(ret)
