from emitpy.emitapp import EmitApp
from emitpy.aircraft import AircraftPerformance

from emitpy.parameters import MANAGED_AIRPORT
from emitpy.utils import actual_time

print(actual_time('2019-04-07T12:55:00+03:00', 'arrival', 10))

e = EmitApp(MANAGED_AIRPORT)

ret = e.do_flight('QR', '969', '2019-04-07T12:55:00+03:00', 'HAN', 'arrival', ('B787', '787'), 'C9', '1fea12', 'A7-BCU', 'RW16L', True)
print(ret)

# ret = e.do_flight("QR", "1", "2022-03-13T14:50:00+02:00", "SYZ", "arrival", "A320", "A7", "abcabc", "A7-PMA", "RW16L")
