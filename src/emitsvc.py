from entity.emitapp import EmitApp
from datetime import datetime

from entity.parameters import MANAGED_AIRPORT

e = EmitApp(MANAGED_AIRPORT)

ret = e.do_service("MATAR", "Fuel", 24, "510", "A321", "FUE51", "aabbcc", "pump", "depot", "depot", datetime.now().isoformat(timespec="seconds"))
print(ret)
