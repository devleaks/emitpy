from emitpy.emitapp import EmitApp
from datetime import datetime, timedelta

from emitpy.parameters import MANAGED_AIRPORT

e = EmitApp(MANAGED_AIRPORT)

ret = e.do_service(queue="raw",
                   emit_rate=30,
                   operator="MATAR",
                   service="sewage",
                   quantity=2,
                   ramp="A9",
                   aircraft="A359",
                   vehicle_model=None,
                   vehicle_ident="FUE51",
                   vehicle_icao24="aabbcc",
                   vehicle_startpos="depot",
                   vehicle_endpos="depot",
                   scheduled=(datetime.now() + timedelta(seconds=10)).isoformat(timespec="seconds"))
print(ret)
