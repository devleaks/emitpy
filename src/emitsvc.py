from emitapp import EmitApp

from entity.parameters import MANAGED_AIRPORT

e = EmitApp(MANAGED_AIRPORT)

ret = e.do_service("MATAR", "Fuel", 24, "510", "A321", "FUE51", "aabbcc", "pump", "depot", "depot", "2022-03-13T14:48:00+02:00")
print(ret)
