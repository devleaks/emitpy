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
logger = logging.getLogger("emitalot")


filename = os.path.join("..", "..", "data", "managedairport", MANAGED_AIRPORT_ICAO, "flights", "2019_W15_ROTATION_RAW.csv")
file = open(filename, "r")
csvdata = csv.DictReader(file)
flights = sorted(csvdata, key=lambda x: (x['FLIGHT ACTUAL TIME_x']))
file.close()

# Parameters
#
NUM_TURNAROUNDS = 5
DO_SERVICE = True
USE_TURNAROUND = False

queue = "raw"
rate = [10, 10]
operator = "QAS"  # for services
fixed_turnaround = timedelta(minutes=90)

cnt_begin = random.randint(0, len(flights)) # random pair of flights
cnt_end = min(cnt_begin + NUM_TURNAROUNDS, len(flights))

# Here we go..
#
logger.info(f"File contains {len(flights)} turnarounds. Generating from {cnt_begin} to {cnt_end}, {NUM_TURNAROUNDS} turnarounds.")
e = EmitApp(MANAGED_AIRPORT_ICAO)

# Internal global vars
now = datetime.now().replace(tzinfo=e.local_timezone)
first_dt = None
icao24 = {}

logger.info("+" + "-" * 100)
logger.info("|")
for i in range(cnt_begin, cnt_end):
    r = flights[i]

    logger.info("| doing turnaround line " + str(i))
    logger.info("|")
    # logger.info("+" + "-" * 100)

    if r['REGISTRATION NO_x'] not in icao24.keys():
        icao24[r['REGISTRATION NO_x']] = f"{random.getrandbits(24):x}"

    ret = None
    arr = None
    dep = None
    arr_est = None

    try:
        movetype = "arrival" if r['IS ARRIVAL_x'] == 'True' else "departure"
        # just for display...
        dtscheduled = datetime.strptime(r['FLIGHT SCHEDULED TIME_x'], "%Y-%m-%d %H:%M:%S").replace(tzinfo=e.timezone)
        # for real time
        dtactual = datetime.strptime(r['FLIGHT ACTUAL TIME_x'], "%Y-%m-%d %H:%M:%S").replace(tzinfo=e.timezone)
        if first_dt is None:
            first_dt = dtactual
        tdiff = dtactual - first_dt
        dtnow = now + tdiff + timedelta(minutes=2)
        logger.info(f"| ARRIVAL {r['AIRLINE CODE_x']}{r['FLIGHT NO_x']}: time diff {first_dt}, {dtactual}, {tdiff} => {dtnow}")
        logger.info("|")

        # Same hour but today:
        # now = datetime.now().replace(tzinfo=e.local_timezone)
        # dtactual = datetime(now.year, now.month, now.day, dt.hour, dt.minute).replace(tzinfo=e.timezone)
        # This is to "time shift" to our local time
        # dtactual = dtactual.replace(tzinfo=e.local_timezone)

        ret = e.do_flight(queue=queue,
                          emit_rate=rate,
                          airline=r['AIRLINE CODE_x'],
                          flightnumber=r['FLIGHT NO_x'],
                          scheduled=dtscheduled.isoformat(),
                          apt=r['AIRPORT_x'],
                          movetype=movetype,
                          actype=(r['AC TYPE_x'], r['AC SUB TYPE_x']),
                          ramp=r['BAY_x'],
                          icao24=icao24[r['REGISTRATION NO_x']],
                          acreg=r['REGISTRATION NO_x'],
                          runway="RW16L",
                          do_services=DO_SERVICE and not USE_TURNAROUND,
                          actual_datetime=dtnow.isoformat())

        if ret.status != 0:
            logger.warning(f"ERROR(arrival) around line {i}: {ret.status}" + ">=" * 30)
            logger.warning(ret)
            logger.warning(f"print(e.do_flight('{r['AIRLINE CODE_x']}', '{r['FLIGHT NO_x']}',"
                + f" '{dtnow.isoformat()}', '{r['AIRPORT_x']}',"
                + f" 'arrival', ('{r['AC TYPE_x']}', '{r['AC SUB TYPE_x']}'), '{r['BAY_x']}',"
                + f" '{icao24[r['REGISTRATION NO_x']]}', '{r['REGISTRATION NO_x']}', 'RW16L'))")
        else:
            arr = ret.data
            arr_est=dtnow.isoformat()
        # arr_est=dtnow.isoformat()
    except:
        if ret is not None:
            logger.error(f"EXCEPTION(arrival) around line {i}: {ret.status}" + ">=" * 30)
            logger.error(ret)

        logger.warning(f"print(e.do_flight('{r['AIRLINE CODE_x']}', '{r['FLIGHT NO_x']}',"
            + f" '{dtnow.isoformat()}', '{r['AIRPORT_x']}',"
            + f" 'arrival', ('{r['AC TYPE_x']}', '{r['AC SUB TYPE_x']}'), '{r['BAY_x']}',"
            + f" '{icao24[r['REGISTRATION NO_x']]}', '{r['REGISTRATION NO_x']}', 'RW16L'))")
        logger.error(traceback.format_exc())

    if arr_est is not None:

        try:
            movetype = "arrival" if r['IS ARRIVAL_y'] == 'True' else "departure"
            # just for display...
            dtscheduled = datetime.strptime(r['FLIGHT SCHEDULED TIME_y'], "%Y-%m-%d %H:%M:%S").replace(tzinfo=e.timezone)
            # for real time
            dtactual = datetime.strptime(r['FLIGHT ACTUAL TIME_y'], "%Y-%m-%d %H:%M:%S").replace(tzinfo=e.timezone)
            dtnow = None
            if fixed_turnaround is not None:
                tdiff = tdiff + fixed_turnaround
                dtnow = datetime.fromisoformat(arr_est) + fixed_turnaround
            else:
                tdiff = dtactual - first_dt
                dtnow = now + tdiff + timedelta(minutes=2)
            logger.info("|")
            logger.info(f"| DEPARTURE {r['AIRLINE CODE_y']}{r['FLIGHT NO_y']}: time diff {first_dt}, {dtactual}, {tdiff} => {dtnow}")
            logger.info("|")

            ret = e.do_flight(queue=queue,
                              emit_rate=rate,
                              airline=r['AIRLINE CODE_y'],
                              flightnumber=r['FLIGHT NO_y'],
                              scheduled=dtscheduled.isoformat(),
                              apt=r['AIRPORT_y'],
                              movetype="departure",
                              actype=(r['AC TYPE_y'], r['AC SUB TYPE_y']),
                              ramp=r['BAY_y'],
                              icao24=icao24[r['REGISTRATION NO_y']],
                              acreg=r['REGISTRATION NO_y'],
                              runway="RW16L",
                              do_services=DO_SERVICE and not USE_TURNAROUND,
                              actual_datetime=dtnow.isoformat())

            if ret.status != 0:
                logger.warning(f"ERROR(departure) around line {i}: {ret.status}" + ">=" * 30)
                logger.warning(ret)
                logger.warning(f"print(e.do_flight('{r['AIRLINE CODE_y']}', '{r['FLIGHT NO_y']}',"
                    + f" '{dtnow.isoformat()}', '{r['AIRPORT_y']}',"
                    + f" 'departure', ('{r['AC TYPE_y']}', '{r['AC SUB TYPE_y']}'), '{r['BAY_y']}',"
                    + f" '{icao24[r['REGISTRATION NO_y']]}', '{r['REGISTRATION NO_y']}', 'RW16L'))")
            else:
                dep = ret.data
                dep_est = dtnow.isoformat()
        except:
            if ret is not None:
                logger.error(f"EXCEPTION(departure) around line {i}: {ret.status}" + ">=" * 30)
                logger.error(ret)
            logger.error(traceback.format_exc())
            logger.warning(f"print(e.do_flight('{r['AIRLINE CODE_y']}', '{r['FLIGHT NO_y']}',"
                + f" '{dtnow.isoformat()}', '{r['AIRPORT_y']}',"
                + f" 'departure', ('{r['AC TYPE_y']}', '{r['AC SUB TYPE_y']}'), '{r['BAY_y']}',"
                + f" '{icao24[r['REGISTRATION NO_y']]}', '{r['REGISTRATION NO_y']}', 'RW16L'))")


        if DO_SERVICE and USE_TURNAROUND:
            try:
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
    else:
        logger.warning(f"ERROR(departure): Arrival flight not generated, cannot generate departure")

    logger.info("|")
    logger.info("| done turnaround line " + str(i))
    logger.info("|")
    logger.info("+" + "-" * 100)
    logger.info("|")

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
