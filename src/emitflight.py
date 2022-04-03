from emitpy.emitapp import EmitApp
from emitpy.aircraft import AircraftPerformance

from emitpy.parameters import MANAGED_AIRPORT

e = EmitApp(MANAGED_AIRPORT)

ret = e.do_flight('QR', '969', '2019-04-07T12:55:00+03:00', 'HAN', 'arrival', 'B787', 'C9', '1fea12', 'A7BCU', 'RW16L', True)
ret = e.do_flight('QR', '163', '2019-04-07T15:35:00+03:00', 'CPH', 'departure', 'B787', 'C9', '1fea12', 'A7BCU', 'RW16L', True)
print(ret)

# ret = e.do_flight("QR", "1", "2022-03-13T14:50:00+02:00", "SYZ", "arrival", "A320", "A7", "abcabc", "A7-PMA", "RW16L")
