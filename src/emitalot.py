import csv
import os
import json
import random
from datetime import datetime, tzinfo, timedelta
import logging

from entity.emitapp import EmitApp
from entity.parameters import MANAGED_AIRPORT
from entity.service import Service
from entity.utils import Timezone

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("testemit")

e = EmitApp(MANAGED_AIRPORT)

dohatime = Timezone(offset=MANAGED_AIRPORT["tzoffset"], name=MANAGED_AIRPORT["tzname"])

filename = os.path.join("..", "data", "managedairport", "OTHH", "flights", "2019_W15_ROTATION_RAW.csv")
file = open(filename, "r")
csvdata = csv.DictReader(file)

icao = {}
cnt = 0
cnt_begin = 0
cnt_end = cnt_begin + 0

for r in csvdata:

    if cnt < cnt_begin:
        cnt = cnt + 1
        continue

    if r['REGISTRATION NO_x'] not in icao.keys():
        icao[r['REGISTRATION NO_x']] = f"{random.getrandbits(24):x}"

    try:
        dt = datetime.strptime(r['FLIGHT SCHEDULED TIME_x'], "%Y-%m-%d %H:%M:%S").replace(tzinfo=dohatime)
        ret = e.do_flight(r['AIRLINE CODE_x'], r['FLIGHT NO_x'], dt.isoformat(), r['AIRPORT_x'],'arrival', (r['AC TYPE_x'], r['AC SUB TYPE_x']),
                          r['BAY_x'], icao[r['REGISTRATION NO_x']], r['REGISTRATION NO_x'], 'RW16L')

        if ret.status != 0:
            logger.warning(f"ERROR around line {cnt}: {ret.status}" + ">=" * 30)
            logger.warning(ret)
            logger.warning(f"print(e.do_flight('{r['AIRLINE CODE_x']}', '{r['FLIGHT NO_x']}',"
                + f" '{dt.isoformat()}', '{r['AIRPORT_x']}',"
                + f" 'arrival', ('{r['AC TYPE_x']}', '{r['AC SUB TYPE_x']}'), '{r['BAY_x']}',"
                + f" '{icao[r['REGISTRATION NO_x']]}', '{r['REGISTRATION NO_x']}', 'RW16L'))")
    except:
        logger.error(f"EXCEPTION around line {cnt}: {ret.status}" + ">=" * 30)
        logger.error(ret)
        logger.warning(f"print(e.do_flight('{r['AIRLINE CODE_x']}', '{r['FLIGHT NO_x']}',"
            + f" '{dt.isoformat()}', '{r['AIRPORT_x']}',"
            + f" 'arrival', ('{r['AC TYPE_x']}', '{r['AC SUB TYPE_x']}'), '{r['BAY_x']}',"
            + f" '{icao[r['REGISTRATION NO_x']]}', '{r['REGISTRATION NO_x']}', 'RW16L'))")


    try:
        dt = datetime.strptime(r['FLIGHT SCHEDULED TIME_y'], "%Y-%m-%d %H:%M:%S").replace(tzinfo=dohatime)
        ret = e.do_flight(r['AIRLINE CODE_y'], r['FLIGHT NO_y'], dt.isoformat(), r['AIRPORT_y'],'arrival', (r['AC TYPE_y'], r['AC SUB TYPE_y']),
                          r['BAY_y'], icao[r['REGISTRATION NO_y']], r['REGISTRATION NO_y'], 'RW16L')

        if ret.status != 0:
            logger.warning(f"ERROR around line {cnt}: {ret.status}" + ">=" * 30)
            logger.warning(ret)
            logger.warning(f"print(e.do_flight('{r['AIRLINE CODE_y']}', '{r['FLIGHT NO_y']}',"
                + f" '{dt.isoformat()}', '{r['AIRPORT_y']}',"
                + f" 'departure', ('{r['AC TYPE_y']}', '{r['AC SUB TYPE_y']}'), '{r['BAY_y']}',"
                + f" '{icao[r['REGISTRATION NO_y']]}', '{r['REGISTRATION NO_y']}', 'RW16L'))")
    except:
        logger.error(f"EXCEPTION around line around line {cnt}: {ret.status}" + ">=" * 30)
        logger.error(ret)
        logger.warning(f"print(e.do_flight('{r['AIRLINE CODE_y']}', '{r['FLIGHT NO_y']}',"
            + f" '{dt.isoformat()}', '{r['AIRPORT_y']}',"
            + f" 'departure', ('{r['AC TYPE_y']}', '{r['AC SUB TYPE_y']}'), '{r['BAY_y']}',"
            + f" '{icao[r['REGISTRATION NO_y']]}', '{r['REGISTRATION NO_y']}', 'RW16L'))")

    cnt = cnt + 1

    if cnt > cnt_end:
        break
