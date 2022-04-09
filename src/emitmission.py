import random

from emitpy.emitapp import EmitApp
from emitpy.aircraft import AircraftPerformance

from emitpy.parameters import MANAGED_AIRPORT
from emitpy.utils import actual_time

print(actual_time('2019-04-07T12:55:00+03:00', 'arrival', 10))

e = EmitApp(MANAGED_AIRPORT)

cp_list = ['checkpoint:0', 'checkpoint:1', 'checkpoint:2', 'checkpoint:3', 'checkpoint:4', 'checkpoint:5',
           'checkpoint:6', 'checkpoint:7', 'checkpoint:8', 'checkpoint:9', 'checkpoint:10', 'checkpoint:11',
           'checkpoint:12', 'checkpoint:13', 'checkpoint:14', 'checkpoint:15', 'checkpoint:16', 'checkpoint:17',
           'checkpoint:18', 'checkpoint:19', 'checkpoint:20', 'checkpoint:21', 'checkpoint:22', 'checkpoint:23',
           'checkpoint:24', 'checkpoint:25', 'checkpoint:26', 'checkpoint:27', 'checkpoint:28', 'checkpoint:29',
           'checkpoint:30', 'checkpoint:31', 'checkpoint:32', 'checkpoint:33', 'checkpoint:34', 'checkpoint:35',
           'checkpoint:36', 'checkpoint:37', 'checkpoint:38']

ret = e.do_mission(operator="Airport Security", checkpoints=random.choices(cp_list, k=3), mission="security",
                   vehicle_ident="JB007", vehicle_icao24="effaca", vehicle_model="Security",
                   vehicle_startpos="svc:depot:0", vehicle_endpos="svc:depot:4", scheduled="2022-04-07T12:55:00+03:00")
print(ret)
