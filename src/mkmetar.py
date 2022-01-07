"""
Test API for flightplandatabase with request caching.

"""
import os
import json
import argparse
import flightplandb as fpdb
from entity.private import FLIGHT_PLAN_DATABASE_APIKEY

# import requests_cache

FP_DIR = os.path.join("..", "data", "metar")

def main():
    parser = argparse.ArgumentParser(description="Get flight plan.")
    parser.add_argument("--icao", "-i", nargs="?", type=str, help="departure")

    args = parser.parse_args()

    orig = args.icao.upper()
    ffp = os.path.join(FP_DIR, orig + ".json")

    # creates file cache
    if not os.path.exists(FP_DIR):
        print("create new fpdb file cache")
        os.mkdir(FP_DIR)

    # not for metar...
    # requests_cache.install_cache()
    api = fpdb.FlightPlanDB(FLIGHT_PLAN_DATABASE_APIKEY)
    metar = api.weather.fetch(icao=orig)
    if metar is not None and metar.METAR is not None:
        metid = metar.METAR[0:4] + '-' + metar.METAR[5:12]
        fn = os.path.join(FP_DIR, metid + ".json")
        if not os.path.exists(fn):
            with open(fn, "w") as outfile:
                json.dump(metar._to_api_dict(), outfile)
        print(json.dumps(metar._to_api_dict()))


if __name__ == "__main__":
    main()

