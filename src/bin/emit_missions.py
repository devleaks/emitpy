"""
This script schedule a number of random missions from now on.
Mission are equally spaced in time.

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

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("emitamission")


filename = os.path.join("..", "..", "data", "managedairport", MANAGED_AIRPORT_ICAO, "flights", "2019_W15_ROTATION_RAW.csv")
file = open(filename, "r")
csvdata = csv.DictReader(file)
flights = sorted(csvdata, key=lambda x: (x['FLIGHT ACTUAL TIME_x']))
file.close()

# Parameters
#
NUM_MISSIONS = 4
sep = timedelta(minutes=4)

name = "emit_mission"
queue = "raw"
rate = 5
operator = "HPD"  # for missions

# Here we go..
#
logger.info(f"Generating {NUM_MISSIONS} missions.")
e = EmitApp(MANAGED_AIRPORT_ICAO)

# Internal global vars
now = datetime.now().replace(tzinfo=e.local_timezone)
first_dt = None

stops = [a[0] for a in e.airport.getPOICombo()]

logger.info("+" + "-" * 100)
logger.info("|")
for i in range(NUM_MISSIONS):
    mty = random.choice(["Fire"]) # "Police", "Security", "Fire",

    logger.info(f"| doing mission {mty} {i}")
    logger.info("|")

    dt = now + i * sep
    icao24 = e.airport.manager.randomICAO24(15)
    ret = None

    ret = e.do_mission(queue=queue,
                        emit_rate=rate,
                        operator=operator,
                        checkpoints=random.choices(stops, k=random.randrange(2, 8)),
                        mission=name,
                        equipment_model=mty,
                        equipment_ident=f"{mty[0]}-{i}-{icao24}",
                        equipment_icao24=icao24,
                        equipment_startpos=random.choice(stops),
                        equipment_endpos=random.choice(stops),
                        scheduled=dt.isoformat())


    if ret.status != 0:
        logger.warning(f"ERROR(mission) around line {i}: {ret.status}" + ">=" * 30)
        logger.warning(ret)
        logger.warning(f"print(e.do_mission())")

    # try:
    #     ret = e.do_mission(queue=queue,
    #                         emit_rate=rate,
    #                         operator=operator,
    #                         checkpoints=[],
    #                         mission=name,
    #                         equipment_model="Police",
    #                         equipment_ident="reg"+str(i),
    #                         equipment_icao24=icao24,
    #                         equipment_startpos="checkpoint:"+random.randrange(30),
    #                         equipment_endpos="checkpoint:"+random.randrange(30),
    #                         scheduled=dt.isoformat())

    #     if ret.status != 0:
    #         logger.warning(f"ERROR(mission) around line {i}: {ret.status}" + ">=" * 30)
    #         logger.warning(ret)
    #         logger.warning(f"print(e.do_mission())")
    # except:
    #     if ret is not None:
    #         logger.error(f"EXCEPTION(mission) around line {i}: {ret.status}" + ">=" * 30)
    #         logger.error(ret)

    logger.info("|")
    logger.info("| done mission " + str(i))
    logger.info("|")
    logger.info("+" + "-" * 100)
    logger.info("|")