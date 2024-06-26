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
from datetime import datetime, timedelta
import logging

from emitpy.emitapp import EmitApp
from emitpy.parameters import MANAGED_AIRPORT_ICAO

FORMAT = "%(levelname)1.1s%(module)22s:%(funcName)-25s%(lineno)4s| %(message)s"
logging.basicConfig(level=logging.DEBUG, format=FORMAT)
logger = logging.getLogger("emit_flights")
logger_error = logging.getLogger("emit_flights_errors")
handler = logging.FileHandler("emit_flights_errors.log")
logger_error.addHandler(handler)

datafile = "flight_table.csv"

filename = os.path.join("..", "..", "data", "managedairport", MANAGED_AIRPORT_ICAO, "flights", datafile)
file = open(filename, "r")
csvdata = csv.DictReader(file)
# flights = sorted(csvdata, key=lambda x: (x['FLIGHT ACTUAL TIME']))  # sorted by actual movement time
flights = list(csvdata)
file.close()

e = EmitApp(MANAGED_AIRPORT_ICAO)

# Parameters
#
queue = "raw"
rate = [15, 10]
DO_SERVICE = False


# NUM_FLIGHTS, cnt_begin = len(flights), 0  # run them all
NUM_FLIGHTS, cnt_begin = 1, random.randint(0, len(flights) - 1)  # run 1, random

procedures = None

# Here we go..
#
cnt_end = min(cnt_begin + NUM_FLIGHTS, len(flights))
idx = cnt_begin - 1
logger.info(f"File contains {len(flights)} flights. Generating from from {cnt_begin} to {cnt_end}.")

# Internal global vars
now = datetime.now().replace(tzinfo=e.local_timezone)
first_dt = None
icao = {}
failed = []

logger.info("\n\n\n+" + "-" * 10 + f" {cnt_begin}-{cnt_end}\n\n")

logger.info("+" + "-" * 100)
logger.info("|")
for r in flights[cnt_begin:cnt_end]:
    """
    IS ARRIVAL;AIRLINE CODE;FLIGHT NO;AIRPORT;FLIGHT SCHEDULED TIME;FLIGHT ACTUAL TIME;
    REGISTRATION NO;AC TYPE;AC TYPE IATA;RAMP
    """
    idx = idx + 1
    logger.info("\n\n\n+" + "-" * 10 + f"DOING {idx}\n\n")

    ret = None

    if r["REGISTRATION NO"] not in icao.keys():
        icao[r["REGISTRATION NO"]] = f"{random.getrandbits(24):x}"

    move = None
    if r["IS ARRIVAL"] == True or r["IS ARRIVAL"] == "True":
        move = "arrival"
    else:
        move = "departure"

    try:
        # just for display...
        dt = datetime.strptime(r["FLIGHT SCHEDULED TIME"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=e.timezone)
        # for real time
        at = datetime.strptime(r["FLIGHT ACTUAL TIME"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=e.timezone)
        if first_dt is None:
            first_dt = at
        tdiff = at - first_dt
        dtnow = now + tdiff + timedelta(minutes=2)
        logger.info(f"| {idx}:{move} {r['AIRLINE CODE']}{r['FLIGHT NO']}: time diff {first_dt}, {at}, {tdiff} => {dtnow}")
        logger.info("|")

        ret = e.do_flight(
            queue=queue,
            emit_rate=rate,
            airline=r["AIRLINE CODE"],
            flightnumber=r["FLIGHT NO"],
            scheduled=dt.isoformat(),
            apt=r["AIRPORT"],
            movetype=move,
            actype=(r["AC TYPE"], r["AC TYPE IATA"]),
            acreg=r["REGISTRATION NO"],
            icao24=icao[r["REGISTRATION NO"]],
            ramp=r["RAMP"],
            runway="RW16L",
            do_services=DO_SERVICE,
            actual_datetime=dtnow.isoformat(),
            comment=f"{datafile}:{idx}",
            forced_procedures=procedures,
        )
    except:
        failed.append(idx)
        logger.error(f"item {r} failed", exc_info=True)
        logger_error.error(f"{datafile}:{idx} forced={procedures}")
        logger_error.error(f"item {r} failed (idx={idx})", exc_info=True)
    finally:
        logger.info(f"{idx}:{ret}")

if len(failed) > 0:
    print("Failed:", failed)
