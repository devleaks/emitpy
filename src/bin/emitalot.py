import csv
import os
import json
import random
import traceback

from datetime import datetime, tzinfo, timedelta
import logging

import sys
sys.path.append('..')

from emitpy.emitapp import EmitApp
from emitpy.parameters import MANAGED_AIRPORT
from emitpy.service import Service
from emitpy.utils import Timezone

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("emitalot")

e = EmitApp(MANAGED_AIRPORT)

dohatime = Timezone(offset=MANAGED_AIRPORT["tzoffset"], name=MANAGED_AIRPORT["tzname"])

filename = os.path.join("..", "..", "data", "managedairport", "OTHH", "flights", "DEMO.csv")
# First: 2019-04-03T03:31:28.911830+03:00
# Last: 2019-04-07T14:38:07.612974+03:00
with open(filename, 'r') as fp:
    numlines = len(fp.readlines())

file = open(filename, "r")
csvdata = csv.DictReader(file)

a = []
for r in csvdata:
    a.append(r)

sorted(a, key=lambda x: (x['FLIGHT SCHEDULED TIME_x']))

# print("Emitalot: number of turnarounds", len(a))

icao = {}

NUM_TURNAROUNDS = 1
DO_SERVICE = False
USE_TURNAROUND = False

cnt = NUM_TURNAROUNDS
cnt_begin = 0 # random.randint(0, len(a)) # random pair of flights
cnt_end = min(cnt_begin + NUM_TURNAROUNDS, len(a))

queue = "test"
rate = 30

# for r in csvdata:
for i in range(cnt_begin, cnt_end):
    r = a[i]

    # if cnt < cnt_begin:
    #     cnt = cnt + 1
    #     continue

    if r['REGISTRATION NO_x'] not in icao.keys():
        icao[r['REGISTRATION NO_x']] = f"{random.getrandbits(24):x}"

    ret = None

    try:
        dt = datetime.strptime(r['FLIGHT SCHEDULED TIME_x'], "%Y-%m-%d %H:%M:%S").replace(tzinfo=dohatime)
        dtactual = datetime.strptime(r['FLIGHT ACTUAL TIME_x'], "%Y-%m-%d %H:%M:%S").replace(tzinfo=dohatime)
        movetype = "arrival" if r['IS ARRIVAL_x'] == 'True' else "departure"

        ret = e.do_flight(queue=queue,
                          emit_rate=rate,
                          airline=r['AIRLINE CODE_x'],
                          flightnumber=r['FLIGHT NO_x'],
                          scheduled=dt.isoformat(),
                          apt=r['AIRPORT_x'],
                          movetype=movetype,
                          actype=(r['AC TYPE_x'], r['AC SUB TYPE_x']),
                          ramp=r['BAY_x'],
                          icao24=icao[r['REGISTRATION NO_x']],
                          acreg=r['REGISTRATION NO_x'],
                          runway="RW16L",
                          do_services=DO_SERVICE and not USE_TURNAROUND,
                          actual_datetime=dtactual.isoformat())

        if ret.status != 0:
            logger.warning(f"ERROR(arrival) around line {cnt}: {ret.status}" + ">=" * 30)
            logger.warning(ret)
            logger.warning(f"print(e.do_flight('{r['AIRLINE CODE_x']}', '{r['FLIGHT NO_x']}',"
                + f" '{dt.isoformat()}', '{r['AIRPORT_x']}',"
                + f" 'arrival', ('{r['AC TYPE_x']}', '{r['AC SUB TYPE_x']}'), '{r['BAY_x']}',"
                + f" '{icao[r['REGISTRATION NO_x']]}', '{r['REGISTRATION NO_x']}', 'RW16L'))")
    except:
        if ret is not None:
            logger.error(f"EXCEPTION(arrival) around line {cnt}: {ret.status}" + ">=" * 30)
            logger.error(ret)

        logger.warning(f"print(e.do_flight('{r['AIRLINE CODE_x']}', '{r['FLIGHT NO_x']}',"
            + f" '{dt.isoformat()}', '{r['AIRPORT_x']}',"
            + f" 'arrival', ('{r['AC TYPE_x']}', '{r['AC SUB TYPE_x']}'), '{r['BAY_x']}',"
            + f" '{icao[r['REGISTRATION NO_x']]}', '{r['REGISTRATION NO_x']}', 'RW16L'))")
        logger.error(traceback.format_exc())


    try:
        dt = datetime.strptime(r['FLIGHT SCHEDULED TIME_y'], "%Y-%m-%d %H:%M:%S").replace(tzinfo=dohatime)
        dtactual = datetime.strptime(r['FLIGHT ACTUAL TIME_y'], "%Y-%m-%d %H:%M:%S").replace(tzinfo=dohatime)
        movetype = "arrival" if r['IS ARRIVAL_y'] == 'True' else "departure"

        ret = e.do_flight(queue=queue,
                          emit_rate=rate,
                          airline=r['AIRLINE CODE_y'],
                          flightnumber=r['FLIGHT NO_y'],
                          scheduled=dt.isoformat(),
                          apt=r['AIRPORT_y'],
                          movetype="departure",
                          actype=(r['AC TYPE_y'], r['AC SUB TYPE_y']),
                          ramp=r['BAY_y'],
                          icao24=icao[r['REGISTRATION NO_y']],
                          acreg=r['REGISTRATION NO_y'],
                          runway="RW16L",
                          do_services=DO_SERVICE and not USE_TURNAROUND,
                          actual_datetime=dtactual.isoformat())

        if ret.status != 0:
            logger.warning(f"ERROR(departure) around line {cnt}: {ret.status}" + ">=" * 30)
            logger.warning(ret)
            logger.warning(f"print(e.do_flight('{r['AIRLINE CODE_y']}', '{r['FLIGHT NO_y']}',"
                + f" '{dt.isoformat()}', '{r['AIRPORT_y']}',"
                + f" 'departure', ('{r['AC TYPE_y']}', '{r['AC SUB TYPE_y']}'), '{r['BAY_y']}',"
                + f" '{icao[r['REGISTRATION NO_y']]}', '{r['REGISTRATION NO_y']}', 'RW16L'))")
    except:
        if ret is not None:
            logger.error(f"EXCEPTION(departure) around line {cnt}: {ret.status}" + ">=" * 30)
            logger.error(ret)
        logger.error(traceback.format_exc())
        logger.warning(f"print(e.do_flight('{r['AIRLINE CODE_y']}', '{r['FLIGHT NO_y']}',"
            + f" '{dt.isoformat()}', '{r['AIRPORT_y']}',"
            + f" 'departure', ('{r['AC TYPE_y']}', '{r['AC SUB TYPE_y']}'), '{r['BAY_y']}',"
            + f" '{icao[r['REGISTRATION NO_y']]}', '{r['REGISTRATION NO_y']}', 'RW16L'))")


    if USE_TURNAROUND:
        try:
            dt = datetime.strptime(r['FLIGHT SCHEDULED TIME_y'], "%Y-%m-%d %H:%M:%S").replace(tzinfo=dohatime)
            movetype = "arrival" if r['IS ARRIVAL_y'] == 'True' else "departure"

            ret = e.do_flight_services(queue="raw",
                                       emit_rate=30)

            if ret.status != 0:
                logger.warning(f"ERROR(departure) around line {cnt}: {ret.status}" + ">=" * 30)
                logger.warning(ret)
                logger.warning(f"print(e.do_flight('{r['AIRLINE CODE_y']}', '{r['FLIGHT NO_y']}',"
                    + f" '{dt.isoformat()}', '{r['AIRPORT_y']}',"
                    + f" 'departure', ('{r['AC TYPE_y']}', '{r['AC SUB TYPE_y']}'), '{r['BAY_y']}',"
                    + f" '{icao[r['REGISTRATION NO_y']]}', '{r['REGISTRATION NO_y']}', 'RW16L'))")
        except:
            if ret is not None:
                logger.error(f"EXCEPTION(departure) around line {cnt}: {ret.status}" + ">=" * 30)
                logger.error(ret)
            logger.error(traceback.format_exc())
            logger.warning(f"print(e.do_flight('{r['AIRLINE CODE_y']}', '{r['FLIGHT NO_y']}',"
                + f" '{dt.isoformat()}', '{r['AIRPORT_y']}',"
                + f" 'departure', ('{r['AC TYPE_y']}', '{r['AC SUB TYPE_y']}'), '{r['BAY_y']}',"
                + f" '{icao[r['REGISTRATION NO_y']]}', '{r['REGISTRATION NO_y']}', 'RW16L'))")


    cnt = cnt + 1

    # if cnt > cnt_end:
    #     break

##
# {
#     'AC SUB TYPE_x': '351',
#     'AC TYPE_x': '351',
#     'AIRLINE CODE_x': 'QR',
#     'AIRPORT_x': 'MCT',
#     'BAY_x': 'E9',
#     'FLIGHT ACTUAL TIME_x': '2019-04-01 00:43:00',
#     'FLIGHT ID_x': '1739338',
#     'FLIGHT NO_x': '1137',
#     'FLIGHT SCHEDULED TIME_x': '2019-04-01 00:05:00',
#     'FLIGHT STATUS_x': 'Y',
#     'FLIGHT TOTAL DELAY_x': '38.0',
#     'IS ARRIVAL_x': 'True',
#     'LINK FLIGHT ID_x': '',
#     'PAIRED_x': '1739432',
#     'REGISTRATION NO_x': 'A7ANB',
#     'TOTAL PAX COUNT_x': '138.0',
#     'TURN AROUND STATUS_x': 'I',
#     'AC SUB TYPE_y': '351',
#     'AC TYPE_y': '351',
#     'AIRLINE CODE_y': 'QR',
#     'AIRPORT_y': 'HND',
#     'BAY_y': 'C1',
#     'FLIGHT ACTUAL TIME_y': '2019-04-01 07:37:00',
#     'FLIGHT ID_y': '1739432',
#     'FLIGHT NO_y': '812',
#     'FLIGHT SCHEDULED TIME_y': '2019-04-01 06:45:00',
#     'FLIGHT STATUS_y': 'Y',
#     'FLIGHT TOTAL DELAY_y': '52.0',
#     'IS ARRIVAL_y': 'False',
#     'LINK FLIGHT ID_y': '',
#     'PAIRED_y': '1739338',
#     'REGISTRATION NO_y': 'A7ANB',
#     'TOTAL PAX COUNT_y': '',
#     'TURN AROUND STATUS_y': 'C'
# }
##
