"""
This script loads a series of flights from a file.
It sorts flights by actual flight time, or scheduled time if actual flight time is not avaialble.
It then selects a number of consecutive flights and schedule them from now on.

"""
import sys
sys.path.append('..')

import csv
import os
import random
from datetime import datetime, tzinfo, timedelta
import logging

from emitpy.emitapp import EmitApp
from emitpy.parameters import MANAGED_AIRPORT_ICAO

FORMAT="%(levelname)1.1s%(module)22s:%(funcName)-25s%(lineno)4s| %(message)s"
logging.basicConfig(level=logging.DEBUG, format=FORMAT)
logger = logging.getLogger("emit_flights")


filename = os.path.join("..", "..", "data", "managedairport", MANAGED_AIRPORT_ICAO, "flights", "flight_table.csv")
file = open(filename, "r")
csvdata = csv.DictReader(file)
flights = sorted(csvdata, key=lambda x: (x['FLIGHT ACTUAL TIME']))  # sorted by actual movement time
file.close()

# Parameters
#
NUM_FLIGHTS = 1
DO_SERVICE = True
queue = "raw"

rate = [15, 10]

cnt = 0
cnt_begin = random.randint(0, len(flights)-1)
cnt_end = cnt_begin + NUM_FLIGHTS

# Here we go..
#
logger.info(f"File contains {len(flights)} flights. Generating from from {cnt_begin} to {cnt_end}.")
e = EmitApp(MANAGED_AIRPORT_ICAO)

# Internal global vars
now = datetime.now().replace(tzinfo=e.local_timezone)
first_dt = None
icao = {}

logger.info("+" + "-" * 10 + f" {cnt_begin}-{cnt_end}")

logger.info("+" + "-" * 100)
logger.info("|")
for r in flights[cnt_begin:cnt_end]:
    """
    IS ARRIVAL;AIRLINE CODE;FLIGHT NO;AIRPORT;FLIGHT SCHEDULED TIME;FLIGHT ACTUAL TIME;
    REGISTRATION NO;AC TYPE;AC TYPE IATA;RAMP
    """
    ret = None

    if r['REGISTRATION NO'] not in icao.keys():
        icao[r['REGISTRATION NO']] = f"{random.getrandbits(24):x}"

    move = None
    if r['IS ARRIVAL'] == True or r['IS ARRIVAL'] == 'True':
        move = "arrival"
    else:
        move = "departure"

    # try:
    # just for display...
    dt = datetime.strptime(r['FLIGHT SCHEDULED TIME'], "%Y-%m-%d %H:%M:%S").replace(tzinfo=e.timezone)
    # for real time
    at = datetime.strptime(r['FLIGHT ACTUAL TIME'], "%Y-%m-%d %H:%M:%S").replace(tzinfo=e.timezone)
    if first_dt is None:
        first_dt = at
    tdiff = at - first_dt
    dtnow = now + tdiff + timedelta(minutes=2)
    logger.info(f"| {move} {r['AIRLINE CODE']}{r['FLIGHT NO']}: time diff {first_dt}, {at}, {tdiff} => {dtnow}")
    logger.info("|")

    ret = e.do_flight(queue=queue,
                      emit_rate=rate,
                      airline=r['AIRLINE CODE'],
                      flightnumber=r['FLIGHT NO'],
                      scheduled=dt.isoformat(),
                      apt=r['AIRPORT'],
                      movetype=move,
                      actype=(r['AC TYPE'], r['AC TYPE IATA']),
                      acreg=r['REGISTRATION NO'],
                      icao24=icao[r['REGISTRATION NO']],
                      ramp=r['RAMP'],
                      runway='RW16L',
                      do_services=DO_SERVICE,
                      actual_datetime=dtnow.isoformat())

    logger.info(f"{ret}")

    if ret is not None and ret.status != 0:
        logger.warning(f"ERROR around line {cnt}: {ret.status}" + ">=" * 30)
        logger.warning(ret)
        logger.warning(f"print(e.do_flight('raw', 30, '{r['AIRLINE CODE']}', '{r['FLIGHT NO']}',"
            + f" '{dt.isoformat()}', '{r['AIRPORT']}',"
            + f" '{move}', ('{r['AC TYPE']}', '{r['AC TYPE IATA']}'), '{r['RAMP']}',"
            + f" '{icao[r['REGISTRATION NO']]}', '{r['REGISTRATION NO']}', 'RW16L'))")

    ## Testing rescheduling
    logger.info(">" *  80)
    emit_key = f"flights:{ret.data}:{rate[0]}:e"
    new_scheduled = dtnow + timedelta(minutes=90)
    sync_name = "TAKE_OFF" if move == "arrival" else "TOUCH_DOWN"
    logger.info(f"new schedule: {emit_key}: {new_scheduled} ({sync_name})")
    ret =e.do_schedule(queue=queue, ident=emit_key, sync=sync_name, scheduled=new_scheduled.isoformat(), do_services=True)

    logger.info(f"{ret}")

    # except Exception as ex:
    #     if ret is not None:
    #         logger.error(f"EXCEPTION around line {cnt}: {ret.status}" + ">=" * 30)
    #         # logger.error(ret, exc_info=True)
    #     else:
    #         logger.error("EXCEPTION but no return status", exc_info=True)

    #     ## logger.error(e)
    #     logger.warning(f"print(e.do_flight('raw', 30, '{r['AIRLINE CODE']}', '{r['FLIGHT NO']}',"
    #         + f" '{dt.isoformat()}', '{r['AIRPORT']}',"
    #         + f" '{move}', ('{r['AC TYPE']}', '{r['AC TYPE IATA']}'), '{r['RAMP']}',"
    #         + f" '{icao[r['REGISTRATION NO']]}', '{r['REGISTRATION NO']}', 'RW16L'))")

    # logger.info("|")
    # logger.info(f"| done {move} {r['AIRLINE CODE']}{r['FLIGHT NO']}: time diff {first_dt}, {at}, {tdiff} => {dtnow}")
    # logger.info("|")
    # logger.info("+" + "-" * 100)
    # logger.info("|")


##
# {
#     'AC SUB TYPE': '351',
#     'AC TYPE': '351',
#     'AIRLINE CODE': 'QR',
#     'AIRPORT': 'MCT',
#     'BAY': 'E9',
#     'FLIGHT ACTUAL TIME': '2019-04-01 00:43:00',
#     'FLIGHT ID': '1739338',
#     'FLIGHT NO': '1137',
#     'FLIGHT SCHEDULED TIME': '2019-04-01 00:05:00',
#     'FLIGHT STATUS': 'Y',
#     'FLIGHT TOTAL DELAY': '38.0',
#     'IS ARRIVAL': 'True',
#     'LINK FLIGHT ID': '',
#     'PAIRED': '1739432',
#     'REGISTRATION NO': 'A7ANB',
#     'TOTAL PAX COUNT': '138.0',
#     'TURN AROUND STATUS': 'I',
# }
##
