import csv
import os
import json
import random
from datetime import datetime, tzinfo, timedelta
"""
AC SUB TYPE_x,
AC TYPE_x,
AIRLINE CODE_x,
AIRPORT_x,
BAY_x,
FLIGHT ACTUAL TIME_x,
FLIGHT ID_x,
FLIGHT NO_x,
FLIGHT SCHEDULED TIME_x,
FLIGHT STATUS_x,
FLIGHT TOTAL DELAY_x,
IS ARRIVAL_x,
LINK FLIGHT ID_x,
PAIRED_x,
REGISTRATION NO_x,
TOTAL PAX COUNT_x,
TURN AROUND STATUS_x,
AC SUB TYPE_y,
AC TYPE_y,
AIRLINE CODE_y,
AIRPORT_y,
BAY_y,
FLIGHT ACTUAL TIME_y,
FLIGHT ID_y,
FLIGHT NO_y,
FLIGHT SCHEDULED TIME_y,
FLIGHT STATUS_y,
FLIGHT TOTAL DELAY_y,
IS ARRIVAL_y,
LINK FLIGHT ID_y,
PAIRED_y,
REGISTRATION NO_y,
TOTAL PAX COUNT_y,
TURN AROUND STATUS_y
"""

filename = os.path.join("..", "..", "data", "managedairport", "OTHH", "flights", "2019_W15_ROTATION_RAW.csv")
file = open(filename, "r")
csvdata = csv.DictReader(file)

icao = {}
# ret = e.do_flight("QR", "1", "2022-03-13T14:50:00+02:00", "SYZ", "arrival", "A320", "A7", "abcabc", "A7-PMA", "RW16L")

class DohaTime(tzinfo):
  def utcoffset(self, dt):
    return timedelta(hours=3)
  def tzname(self, dt):
    return "Doha"

dohatime = DohaTime()

for r in csvdata:

    if r['REGISTRATION NO_x'] not in icao.keys():
        icao[r['REGISTRATION NO_x']] = f"{random.getrandbits(24):x}"

    dt = datetime.strptime(r['FLIGHT SCHEDULED TIME_x'], "%Y-%m-%d %H:%M:%S").replace(tzinfo=dohatime)
    print(f"e.do_flight('{r['AIRLINE CODE_x']}', '{r['FLIGHT NO_x']}',"
        + f" '{dt.isoformat()}', '{r['AIRPORT_x']}',"
        + f" 'arrival', '{r['AC TYPE_x']}', '{r['BAY_x']}',"
        + f" '{icao[r['REGISTRATION NO_x']]}', '{r['REGISTRATION NO_x']}', 'RW16L')")

    dt = datetime.strptime(r['FLIGHT SCHEDULED TIME_y'], "%Y-%m-%d %H:%M:%S").replace(tzinfo=dohatime)
    print(f"e.do_flight('{r['AIRLINE CODE_y']}', '{r['FLIGHT NO_y']}',"
        + f" '{dt.isoformat()}', '{r['AIRPORT_y']}',"
        + f" 'departure', '{r['AC TYPE_y']}', '{r['BAY_y']}',"
        + f" '{icao[r['REGISTRATION NO_y']]}', '{r['REGISTRATION NO_y']}', 'RW16L')")

