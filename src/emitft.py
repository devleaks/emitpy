import csv
import os
import json
import random
from datetime import datetime, tzinfo, timedelta
import logging

from emitpy.emitapp import EmitApp
from emitpy.parameters import MANAGED_AIRPORT
from emitpy.service import Service
from emitpy.utils import Timezone

# logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("emitft")

e = EmitApp(MANAGED_AIRPORT)

dohatime = Timezone(offset=MANAGED_AIRPORT["tzoffset"], name=MANAGED_AIRPORT["tzname"])

filename = os.path.join("..", "data", "managedairport", "OTHH", "flights", "flight_table.csv")
file = open(filename, "r")
csvdata = csv.DictReader(file)

icao = {}
cnt = 0
cnt_begin = 0
cnt_end = cnt_begin + 600

for r in csvdata:
    """
    IS ARRIVAL;AIRLINE CODE;FLIGHT NO;AIRPORT;FLIGHT SCHEDULED TIME;FLIGHT ACTUAL TIME;
    REGISTRATION NO;AC TYPE;AC TYPE IATA;RAMP
    """
    if cnt < cnt_begin:
        cnt = cnt + 1
        continue

    if r['REGISTRATION NO'] not in icao.keys():
        icao[r['REGISTRATION NO']] = f"{random.getrandbits(24):x}"

    move = None
    if r['IS ARRIVAL'] == True or r['IS ARRIVAL'] == 'True':
        move = "arrival"
    else:
        move = "departure"

    try:
        dt = datetime.strptime(r['FLIGHT SCHEDULED TIME'], "%Y-%m-%d %H:%M:%S").replace(tzinfo=dohatime)
        at = datetime.strptime(r['FLIGHT ACTUAL TIME'], "%Y-%m-%d %H:%M:%S").replace(tzinfo=dohatime)
        ret = e.do_flight(queue="raw",
                          emit_rate=30,
                          airline=r['AIRLINE CODE'],
                          flightnumber=r['FLIGHT NO'],
                          scheduled=dt.isoformat(),
                          apt=r['AIRPORT'],
                          movetype=move,
                          acarr=(r['AC TYPE'], r['AC TYPE IATA']),
                          acreg=r['REGISTRATION NO'],
                          icao24=icao[r['REGISTRATION NO']],
                          ramp=r['RAMP'],
                          runway='RW16L',
                          do_services=True,
                          actual_datetime=at.isoformat())

        if ret.status != 0:
            logger.warning(f"ERROR around line {cnt}: {ret.status}" + ">=" * 30)
            logger.warning(ret)
            logger.warning(f"print(e.do_flight('raw', 30, '{r['AIRLINE CODE']}', '{r['FLIGHT NO']}',"
                + f" '{dt.isoformat()}', '{r['AIRPORT']}',"
                + f" '{move}', ('{r['AC TYPE']}', '{r['AC TYPE IATA']}'), '{r['RAMP']}',"
                + f" '{icao[r['REGISTRATION NO']]}', '{r['REGISTRATION NO']}', 'RW16L'))")

    except Exception as ex:
        logger.error(f"EXCEPTION around line {cnt}: {ret.status}" + ">=" * 30)
        logger.error(ret)
        ## logger.error(e)
        logger.warning(f"print(e.do_flight('raw', 30, '{r['AIRLINE CODE']}', '{r['FLIGHT NO']}',"
            + f" '{dt.isoformat()}', '{r['AIRPORT']}',"
            + f" '{move}', ('{r['AC TYPE']}', '{r['AC TYPE IATA']}'), '{r['RAMP']}',"
            + f" '{icao[r['REGISTRATION NO']]}', '{r['REGISTRATION NO']}', 'RW16L'))")

    cnt = cnt + 1
    if cnt > cnt_end:
        break
