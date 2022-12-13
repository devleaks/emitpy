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

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("emitalot")


filename = os.path.join("..", "..", "data", "managedairport", MANAGED_AIRPORT_ICAO, "flights", "2019_W15_ROTATION_RAW.csv")
with open(filename, "r") as fp:
    numlines = len(fp.readlines())

file = open(filename, "r")
csvdata = csv.DictReader(file)

a = []
for r in csvdata:
    a.append(r)

sorted(a, key=lambda x: (x['FLIGHT SCHEDULED TIME_x']))

# print("Emitalot: number of turnarounds", len(a))

NUM_TURNAROUNDS = 1
DO_SERVICE = True
USE_TURNAROUND = False


cnt_begin = random.randint(0, len(a)) # random pair of flights
cnt_end = min(cnt_begin + NUM_TURNAROUNDS, len(a))


icao24 = {}
queue = "raw"
rate = [10, 10]


# Here we go
e = EmitApp(MANAGED_AIRPORT_ICAO)

for i in range(cnt_begin, cnt_end):
    r = a[i]

    logger.info("+" + "-" * 100)
    logger.info("| doing turnaround line " + str(i))
    # logger.info("+" + "-" * 100)

    if r['REGISTRATION NO_x'] not in icao24.keys():
        icao24[r['REGISTRATION NO_x']] = f"{random.getrandbits(24):x}"

    ret = None
    arr = None
    dep = None

    try:
        movetype = "arrival" if r['IS ARRIVAL_x'] == 'True' else "departure"
        dt = datetime.strptime(r['FLIGHT SCHEDULED TIME_x'], "%Y-%m-%d %H:%M:%S").replace(tzinfo=e.timezone)
        dtactual = datetime.now().replace(tzinfo=e.local_timezone) + timedelta(minutes=2) # datetime.strptime(r['FLIGHT ACTUAL TIME_x'], "%Y-%m-%d %H:%M:%S").replace(tzinfo=e.timezone)

        # Same hour but today:
        # now = datetime.now().replace(tzinfo=e.local_timezone)
        # dtactual = datetime(now.year, now.month, now.day, dt.hour, dt.minute).replace(tzinfo=e.timezone)
        # This is to "time shift" to our local time
        # dtactual = dtactual.replace(tzinfo=e.local_timezone)

        ret = e.do_flight(queue=queue,
                          emit_rate=rate,
                          airline=r['AIRLINE CODE_x'],
                          flightnumber=r['FLIGHT NO_x'],
                          scheduled=dt.isoformat(),
                          apt=r['AIRPORT_x'],
                          movetype=movetype,
                          actype=(r['AC TYPE_x'], r['AC SUB TYPE_x']),
                          ramp=r['BAY_x'],
                          icao24=icao24[r['REGISTRATION NO_x']],
                          acreg=r['REGISTRATION NO_x'],
                          runway="RW16L",
                          do_services=DO_SERVICE and not USE_TURNAROUND,
                          actual_datetime=dtactual.isoformat())

        if ret.status != 0:
            logger.warning(f"ERROR(arrival) around line {i}: {ret.status}" + ">=" * 30)
            logger.warning(ret)
            logger.warning(f"print(e.do_flight('{r['AIRLINE CODE_x']}', '{r['FLIGHT NO_x']}',"
                + f" '{dt.isoformat()}', '{r['AIRPORT_x']}',"
                + f" 'arrival', ('{r['AC TYPE_x']}', '{r['AC SUB TYPE_x']}'), '{r['BAY_x']}',"
                + f" '{icao24[r['REGISTRATION NO_x']]}', '{r['REGISTRATION NO_x']}', 'RW16L'))")
        else:
            arr = ret.data
            arr_est=dtactual.isoformat()
    except:
        if ret is not None:
            logger.error(f"EXCEPTION(arrival) around line {i}: {ret.status}" + ">=" * 30)
            logger.error(ret)

        logger.warning(f"print(e.do_flight('{r['AIRLINE CODE_x']}', '{r['FLIGHT NO_x']}',"
            + f" '{dt.isoformat()}', '{r['AIRPORT_x']}',"
            + f" 'arrival', ('{r['AC TYPE_x']}', '{r['AC SUB TYPE_x']}'), '{r['BAY_x']}',"
            + f" '{icao24[r['REGISTRATION NO_x']]}', '{r['REGISTRATION NO_x']}', 'RW16L'))")
        logger.error(traceback.format_exc())


    try:
        movetype = "arrival" if r['IS ARRIVAL_y'] == 'True' else "departure"
        dt = datetime.strptime(r['FLIGHT SCHEDULED TIME_y'], "%Y-%m-%d %H:%M:%S").replace(tzinfo=e.timezone)
        dtactual = datetime.now().replace(tzinfo=e.local_timezone) + timedelta(minutes=90)  # datetime.strptime(r['FLIGHT ACTUAL TIME_y'], "%Y-%m-%d %H:%M:%S").replace(tzinfo=e.timezone)

        ret = e.do_flight(queue=queue,
                          emit_rate=rate,
                          airline=r['AIRLINE CODE_y'],
                          flightnumber=r['FLIGHT NO_y'],
                          scheduled=dt.isoformat(),
                          apt=r['AIRPORT_y'],
                          movetype="departure",
                          actype=(r['AC TYPE_y'], r['AC SUB TYPE_y']),
                          ramp=r['BAY_y'],
                          icao24=icao24[r['REGISTRATION NO_y']],
                          acreg=r['REGISTRATION NO_y'],
                          runway="RW16L",
                          do_services=DO_SERVICE and not USE_TURNAROUND,
                          actual_datetime=dtactual.isoformat())

        if ret.status != 0:
            logger.warning(f"ERROR(departure) around line {i}: {ret.status}" + ">=" * 30)
            logger.warning(ret)
            logger.warning(f"print(e.do_flight('{r['AIRLINE CODE_y']}', '{r['FLIGHT NO_y']}',"
                + f" '{dt.isoformat()}', '{r['AIRPORT_y']}',"
                + f" 'departure', ('{r['AC TYPE_y']}', '{r['AC SUB TYPE_y']}'), '{r['BAY_y']}',"
                + f" '{icao24[r['REGISTRATION NO_y']]}', '{r['REGISTRATION NO_y']}', 'RW16L'))")
        else:
            dep = ret.data
            dep_est = dtactual.isoformat()
    except:
        if ret is not None:
            logger.error(f"EXCEPTION(departure) around line {i}: {ret.status}" + ">=" * 30)
            logger.error(ret)
        logger.error(traceback.format_exc())
        logger.warning(f"print(e.do_flight('{r['AIRLINE CODE_y']}', '{r['FLIGHT NO_y']}',"
            + f" '{dt.isoformat()}', '{r['AIRPORT_y']}',"
            + f" 'departure', ('{r['AC TYPE_y']}', '{r['AC SUB TYPE_y']}'), '{r['BAY_y']}',"
            + f" '{icao24[r['REGISTRATION NO_y']]}', '{r['REGISTRATION NO_y']}', 'RW16L'))")


    if DO_SERVICE and USE_TURNAROUND:
        try:
            dt = datetime.strptime(r['FLIGHT SCHEDULED TIME_y'], "%Y-%m-%d %H:%M:%S").replace(tzinfo=e.timezone)
            movetype = "arrival" if r['IS ARRIVAL_y'] == 'True' else "departure"

            operator = "QAS"
            ret = e.do_turnaround(queue=queue,
                                  emit_rate=rate,
                                  operator=operator,
                                  arrival=arr,
                                  departure=dep,
                                  estimated=arr_est)

            if ret.status != 0:
                logger.warning(f"ERROR(turnaround) around line {i}: {ret.status}" + ">=" * 30)
                logger.warning(ret)
                logger.warning(f"print(e.do_turnaround(queue='{queue}'', emit_rate={rate}, operator='{operator}',"
                             + f" arrival='{arr}', departure='{dep}', estimated='{arr_est}')")
        except:
            if ret is not None:
                logger.error(f"EXCEPTION(departure) around line {i}: {ret.status}" + ">=" * 30)
                logger.error(ret)
            logger.error(traceback.format_exc())
            logger.warning(f"print(e.do_turnaround(queue='{queue}'', emit_rate={rate}, operator='{operator}',"
                         + f" arrival='{arr}', departure='{dep}', estimated='{arr_est}', departure_estimate='{dep_est}')")

    logger.info("| done turnaround line " + str(i))
    logger.info("+" + "-" * 100)

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
