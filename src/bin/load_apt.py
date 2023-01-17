"""
This script loads a series of flights from a file.
It sorts flights by actual flight time, or scheduled time if actual flight time is not avaialble.
It then selects a number of consecutive flights and schedule them from now on.

"""
import sys
sys.path.append('..')

import json
import os
from datetime import datetime, tzinfo, timedelta
import logging

from emitpy.emitapp import EmitApp
from emitpy.parameters import MANAGED_AIRPORT_ICAO

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("loadapt")


a = EmitApp(MANAGED_AIRPORT_ICAO)

