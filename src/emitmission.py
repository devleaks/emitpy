import logging
import random

from emitpy.emitapp import EmitApp
from emitpy.aircraft import AircraftPerformance

from emitpy.parameters import MANAGED_AIRPORT
from emitpy.utils import actual_time

logging.basicConfig(level=logging.DEBUG)

print(actual_time('2019-04-07T12:55:00+03:00', 'arrival', 10))

e = EmitApp(MANAGED_AIRPORT)

ret = e.do_mission(queue="raw",
                   emit_rate=30,
                   operator="Airport Security",
                   checkpoints=[],
                   mission="security",
                   vehicle_ident="JB007",
                   vehicle_icao24="effaca",
                   vehicle_model="Security",
                   vehicle_startpos="svc:depot:0",
                   vehicle_endpos="svc:depot:4",
                   scheduled="2022-04-07T12:55:00+03:00")

print(ret)
