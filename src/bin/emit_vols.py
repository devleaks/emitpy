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
from emitpy.airport import Airport
from emitpy.aircraft import AircraftType, AircraftTypeWithPerformance

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("emit_vols")


filename = os.path.join("..", "..", "data", "managedairport", MANAGED_AIRPORT_ICAO, "flights", "vols.csv")
flights = []
with open(filename, "r") as file:
    csvdata = csv.DictReader(file)
    flights = sorted(csvdata, key=lambda x: (x['FLIGHT ACTUAL TIME']))  # sorted by actual movement time

# Parameters
#
# Problems:
# 61134-61135
# 8817-8818
# 4652-4653: no flight route
#
#
restricted_list = ['A20N', 'A21N', 'A320', 'A321', 'A332', 'A333', 'A338', 'A339', 'A342', 'A343', 'A345', 'A346', 'A359', 'A35K',
                   'B737', 'B738', 'B739', 'B741', 'B742', 'B743', 'B744', 'B748', 'B74D', 'B74R', 'B74S', 'B772', 'B773', 'B77L', 'B77W', 'B788']
NUM_FLIGHTS = 1
DO_SERVICE = True
queue = "raw"
rate = [15, 10]
cnt = 0
cnt_begin = random.randint(0, len(flights)-1)
cnt_end = cnt_begin + NUM_FLIGHTS
logger.info(f"File contains {len(flights)} flights. Generating from from {cnt_begin} to {cnt_end}.")

e = EmitApp(MANAGED_AIRPORT_ICAO)

# Internal global vars
first_dt = None
icao = {}
now = datetime.now().replace(tzinfo=e.local_timezone)
valid_ramps = list(e.airport.getRamps().keys())

logger.info("+" + "-" * 10 + f" {cnt_begin}-{cnt_end}")
logger.info("+" + "-" * 100)
logger.info("|")

for r in flights[cnt_begin:cnt_end]:
    """
    IS ARRIVAL,FLTNR,AIRLINE IATA,FLT_NUMBERIATA,FLTNR_ICAO,AIRLINE ICAO,FLT_NUMBER_ICAO,AIRPORT,
    FLIGHT SCHEDULED TIME,FLIGHT ACTUAL TIME,REGISTRATION NO,AC TYPE,AC TYPE IATA,RAMP,CATEGORIE
    """
    ret = None

    # Generate an aircraft
    r['REGISTRATION NO'] = r['FLTNR']
    if r['REGISTRATION NO'] not in icao.keys():
        icao[r['REGISTRATION NO']] = f"{random.getrandbits(24):x}"
    # now get a aircraft capable of flying the distance...
    r['AC TYPE'] = 'A320'
    opposite = Airport.findIATA(r['AIRPORT'], e.use_redis())
    if opposite is not None:
        dist = e.airport.miles(opposite)
        if dist > 0:
            ac = AircraftTypeWithPerformance.findAircraftForRange(dist, restricted_list=restricted_list, redis=e.use_redis())
            if ac is not None:
                r['AC TYPE'] = ac.typeId

    move = None
    if r['IS ARRIVAL'] == True or r['IS ARRIVAL'] == 'True' or r['IS ARRIVAL'] == 'A':
        move = "arrival"
    else:
        move = "departure"

    if r['RAMP'] not in valid_ramps:
        ramp = random.choice(valid_ramps)
        logger.info(f"| {move} {r['AIRLINE IATA']}{r['FLT_NUMBERIATA']}: ramp {r['RAMP']} unknown, using random assignment {ramp}")
        r['RAMP'] = ramp
    # else:
    #     logger.info(f"| {move} {r['AIRLINE IATA']}{r['FLT_NUMBERIATA']}: ramp {r['RAMP']} found")

    logger.info(f"| {move} {r['AIRLINE IATA']}{r['FLT_NUMBERIATA']} ({round(dist)} mi.): created {r['AC TYPE']} reg. {r['REGISTRATION NO']} icao24 {icao[r['REGISTRATION NO']]}")

    try:
        # correct date format: 02-JAN-17 12:55:00 AM +01:00
        # s = "".join(r['FLIGHT SCHEDULED TIME'].rsplit(":", 1))
        # print(">>>>>>", r['FLIGHT SCHEDULED TIME'], s)
        dt = datetime.strptime(r['FLIGHT SCHEDULED TIME'], "%Y-%m-%d %H:%M:%S%z").replace(tzinfo=e.timezone)
        # print(">>>>>>", dt.isoformat())

        # for real time
        at = datetime.strptime(r['FLIGHT ACTUAL TIME'], "%Y-%m-%d %H:%M:%S%z").replace(tzinfo=e.timezone)
        if first_dt is None:
            first_dt = at
        tdiff = at - first_dt
        dtnow = now + tdiff + timedelta(minutes=2)
        logger.info(f"| {move} {r['AIRLINE IATA']}{r['FLT_NUMBERIATA']}: time diff {first_dt}, {at}, {tdiff} => {dtnow}")
        logger.info( "|")

        ret = e.do_flight(queue=queue,
                          emit_rate=rate,
                          airline=r['AIRLINE IATA'],
                          flightnumber=r['FLT_NUMBERIATA'],
                          scheduled=dt.isoformat(),
                          apt=r['AIRPORT'],
                          movetype=move,
                          actype=r['AC TYPE'],
                          acreg=r['REGISTRATION NO'],
                          icao24=icao[r['REGISTRATION NO']],
                          ramp=r['RAMP'],
                          do_services=DO_SERVICE,
                          actual_datetime=dtnow.isoformat())

        if ret is not None and ret.status != 0:
            logger.warning(f"ERROR around line {cnt}: {ret.status}" + ">=" * 30)
            logger.warning(ret)
            logger.warning(f"print(e.do_flight('raw', 30, '{r['AIRLINE IATA']}', '{r['FLT_NUMBERIATA']}',"
                + f" '{dt.isoformat()}', '{r['AIRPORT']}',"
                + f" '{move}', '{r['AC TYPE']}', '{r['RAMP']}',"
                + f" '{icao[r['REGISTRATION NO']]}', '{r['REGISTRATION NO']}', 'RW22L'))")

    except Exception as ex:
        if ret is not None:
            logger.error(f"EXCEPTION around line {cnt}: {ret.status}" + ">=" * 30)
            # logger.error(ret, exc_info=True)
        else:
            logger.error("EXCEPTION but no return status", exc_info=True)

        ## logger.error(e)
            logger.warning(f"print(e.do_flight('raw', 30, '{r['AIRLINE IATA']}', '{r['FLT_NUMBERIATA']}',"
                + f" '{dt.isoformat()}', '{r['AIRPORT']}',"
                + f" '{move}', '{r['AC TYPE']}', '{r['RAMP']}',"
                + f" '{icao[r['REGISTRATION NO']]}', '{r['REGISTRATION NO']}', 'RW22L'))")

    logger.info( "|")
    logger.info(f"| done {move} {r['AIRLINE IATA']}{r['FLT_NUMBERIATA']}: time diff {first_dt}, {at}, {tdiff} => {dtnow}")
    logger.info( "|")
    logger.info( "+" + "-" * 100)
    logger.info( "|")
