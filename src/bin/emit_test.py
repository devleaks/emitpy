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

from emitpy.geo import Movement, FeatureWithProps
from emitpy.emit import Emit

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("emit_test")

filename = os.path.join("..", "..", "db", MANAGED_AIRPORT_ICAO, "debug", "debug-QR193-S201904010610-2023-01-23T17:41:25.004552-debug-move-move-data.geojson")
movedata = None
with open(filename, "r") as file:
    movedata = json.load(file)

a = EmitApp(MANAGED_AIRPORT_ICAO)

m = Movement(airport=a._managedairport)
m.moves = FeatureWithProps.betterFeatures(movedata["features"])
e = Emit(move=m)
e.emit_type = "service"
e.emit(frequency=10)
