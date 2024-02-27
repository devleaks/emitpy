"""
This script loads a series of flights from a file.
It sorts flights by actual flight time, or scheduled time if actual flight time is not avaialble.
It then selects a number of consecutive flights and schedule them from now on.

"""
import sys

sys.path.append("..")

import csv
import os
import logging
import shutil

from emitpy.emitapp import EmitApp
from emitpy.parameters import MANAGED_AIRPORT_ICAO, XPLANE_DIR
from emitpy.airport import Airport


FORMAT = "%(levelname)1.1s%(module)22s:%(funcName)-25s%(lineno)4s| %(message)s"
logging.basicConfig(level=logging.DEBUG, format=FORMAT)
logger = logging.getLogger("emit_flights")


filename = os.path.join("..", "..", "data", "managedairport", MANAGED_AIRPORT_ICAO, "flights", "apts.txt")
file = open(filename, "r")
data = file.readlines()
file.close()

directory = os.path.join(XPLANE_DIR, "Resources", "CIFP")
if not os.path.exists(directory):
    os.mkdir(directory)

err = []
e = EmitApp(MANAGED_AIRPORT_ICAO)

for a in data:
    a = a.strip("\n")
    apt = Airport.findIATA(a)
    if apt is not None:
        cifp = os.path.join(XPLANE_DIR, "Resources", "default data", "CIFP", apt.icao + ".dat")
        if os.path.exists(cifp):
            dst = os.path.join(directory, apt.icao + ".dat")
            shutil.copyfile(cifp, dst)
            print(",".join([a, apt.iata, dst]))
        else:
            print("ERROR: NO CIFP: ", a, apt.icao)
            err.append(apt.icao)
    else:
        print("ERROR: NO APT", a)

print("Errors:", err)
