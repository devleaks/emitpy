from entity.emitapp import EmitApp
from entity.aircraft import AircraftPerformance

from entity.parameters import MANAGED_AIRPORT

e = EmitApp(MANAGED_AIRPORT)

ret = e.do_flight('QR', '969', '2019-04-07T12:55:00+03:00', 'HAN', 'arrival', AircraftPerformance.getEquivalence('B787'), 'C9', '1fea12', 'A7BCU', 'RW16L')
print(ret)

# ret = e.do_flight("QR", "1", "2022-03-13T14:50:00+02:00", "SYZ", "arrival", "A320", "A7", "abcabc", "A7-PMA", "RW16L")
