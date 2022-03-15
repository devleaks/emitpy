from emitapp import EmitApp

from entity.parameters import MANAGED_AIRPORT

e = EmitApp(MANAGED_AIRPORT)

ret = e.do_flight("QR", "1", "2022-03-13T14:50:00+02:00", "SYZ", "arrival", "A320", "A7", "abcabc", "A7-PMA", "RW16L")
print(ret)
