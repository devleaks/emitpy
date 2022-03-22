from entity.emitapp import EmitApp
from datetime import datetime, timedelta

from entity.parameters import MANAGED_AIRPORT

e = EmitApp(MANAGED_AIRPORT)

ret = e.do_service("MATAR", "sewage", 24, "A9", "A359", "FUE51", "aabbcc", None, "depot", "depot", (datetime.now() + timedelta(seconds=10)).isoformat(timespec="seconds"))
print(ret)
