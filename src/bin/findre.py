"""
This script loads a series of turnarounds (pairs of flights) from a file.
It sorts turnaround by actual arrival flight time, or scheduled time if actual flight time is not available.
It then selects a number of consecutive turnarounds and schedule them from now on,
respecting the time difference between flights.
Optionally, the time between arrival and departure can be set to a fixed value, ignoring the actual departure times.
"""
import sys
sys.path.append('..')

import csv
import os
import json
import random
import traceback
import logging

from datetime import datetime, tzinfo, timedelta

from emitpy.emitapp import EmitApp
from emitpy.parameters import MANAGED_AIRPORT_ICAO
from emitpy.utils import Timezone

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("findre")


e = EmitApp(MANAGED_AIRPORT_ICAO)
