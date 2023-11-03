"""
This script schedule a number of random missions from now on.
Mission are equally spaced in time.

"""
import sys

sys.path.append("..")

import csv
import os
import json
import random
import traceback
import logging

from datetime import datetime, tzinfo, timedelta

from emitpy.emitapp import EmitApp
from emitpy.parameters import MANAGED_AIRPORT_ICAO

FORMAT = "%(levelname)1.1s%(module)22s:%(funcName)-25s%(lineno)4s| %(message)s"
logging.basicConfig(level=logging.DEBUG, format=FORMAT)
logger = logging.getLogger("emitaservice")

# Parameters
#
NUM_MISSIONS = 1

name = "emit_service"
queue = "raw"
rate = 10
operator = "HAS"  # for missions

# Here we go..
#
logger.info(f"Generating one service.")
e = EmitApp(MANAGED_AIRPORT_ICAO)
stops = [a[0] for a in e.airport.getPOICombo()]

# Internal global vars
now = datetime.now().replace(tzinfo=e.local_timezone) + timedelta(seconds=20)

logger.info("+" + "-" * 100)
logger.info("|")

logger.info(f"| doing service")
logger.info("|")

dt = now
icao24 = e.airport.manager.randomICAO24(15)

# def do_service(
#     self,
#     queue,
#     emit_rate,
#     operator,
#     service,
#     quantity,
#     ramp,
#     aircraft,
#     equipment_ident,
#     equipment_icao24,
#     equipment_model,
#     equipment_startpos,
#     equipment_endpos,
#     scheduled,
# ):
#
start_pos = "ramp:C9"  # random.choice(stops)
end_pos = "ramp:Q4"  # random.choice(stops)
# print(">>", start_pos, end_pos)

ret = e.do_service(
    queue=queue,
    emit_rate=rate,
    operator=operator,
    service="baggage",
    ramp="E7",
    aircraft="B777",
    quantity=1,
    equipment_model="small-train",
    equipment_ident=f"baggage-{icao24}",
    equipment_icao24=icao24,
    equipment_startpos=start_pos,
    equipment_endpos=end_pos,
    scheduled=dt.isoformat(),
)

if ret.status != 0:
    logger.warning(f"ERROR(service): {ret.status}" + ">=" * 30)
    logger.warning(ret)
    logger.warning(f"print(e.do_service())")

logger.error(ret)

logger.info("|")
logger.info("| done service")
logger.info("|")
logger.info("+" + "-" * 100)
logger.info("|")
