from entity.emitapp import EmitApp
from datetime import datetime, timedelta

from entity.parameters import MANAGED_AIRPORT

e = EmitApp(MANAGED_AIRPORT)

ret = e.do_service("MATAR", "fuel", 24, "A7", "A321", "FUE51", "aabbcc", "pump", "depot", "depot", (datetime.now() + timedelta(seconds=10)).isoformat(timespec="seconds"))
print(ret)
