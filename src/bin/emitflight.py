from __future__ import annotations
import sys
sys.path.append('/Users/pierre/Developer/oscars/emitpy/src')

import logging

from emitpy.emitapp import EmitApp
from emitpy.aircraft import AircraftPerformance

from emitpy.parameters import MANAGED_AIRPORT
from emitpy.utils import actual_time

logging.basicConfig(level=logging.DEBUG)

e = EmitApp(MANAGED_AIRPORT)

ret = e.do_flight(queue="raw",
                  emit_rate=30,
                  airline="QR",
                  flightnumber="969",
                  scheduled="2019-04-07T12:55:00+03:00",
                  apt="HAN",
                  movetype="arrival",
                  acarr=("B787", "787"),
                  ramp="C9",
                  icao24="1fea12",
                  acreg="A7-BCU",
                  runway="RW16L",
                  do_services=True)

print(ret)
