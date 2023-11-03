"""
This script loads a series of flights from a file.
It sorts flights by actual flight time, or scheduled time if actual flight time is not avaialble.
It then selects a number of consecutive flights and schedule them from now on.

"""
import sys

sys.path.append("..")

import csv
import os
import random
from datetime import datetime, tzinfo, timedelta
import logging

from emitpy.emitapp import EmitApp
from emitpy.parameters import MANAGED_AIRPORT_ICAO
from emitpy.airspace import FlightPlan

FORMAT = "%(levelname)1.1s%(module)22s:%(funcName)-25s%(lineno)4s| %(message)s"
logging.basicConfig(level=logging.DEBUG, format=FORMAT)
logger = logging.getLogger("emit_flights")

e = EmitApp(MANAGED_AIRPORT_ICAO)

# Internal global vars
now = datetime.now().replace(tzinfo=e.local_timezone)

fp = FlightPlan("SN123", "EBBR", "OTHH")
fp.aerospace = e.airport.airspace
fp.parse("EBBR LIRSU UZ315 RIDAR UZ738 UNKEN UL603 LATLO 4700N01400E KFT VALLU")
