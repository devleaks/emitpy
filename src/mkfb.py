"""
Make a random flight board from startdate to enddate.
Usage:
    python mkfb.py count "2021-05-05T10:06:23+02:00" 4

"""
import argparse
import logging
from datetime import datetime

logging.basicConfig(level=logging.DEBUG)  # filename=('mkfb.log')

logger = logging.getLogger("mkfb")

from entity import Flightboard
from emitpy.airport import ManagedAirport
from entity import Constant


def main():
    parser = argparse.ArgumentParser(description="Generate flight board.")
    subparsers = parser.add_subparsers(title='subparsers')
    bydates = subparsers.add_parser('dates')
    bydates.add_argument("startdate", type=str, help="start date for flightboard (default to now)",
                         nargs='?', default=datetime.now().isoformat())
    bydates.add_argument("enddate", type=str, help="end date for flightboard")
    bycount = subparsers.add_parser('count')
    bycount.add_argument("startdate", type=str, help="start date for flightboard (default to now)",
                         nargs='?', default=datetime.now().isoformat())
    bycount.add_argument("count", type=int, help="number of flights to generate")

    args = parser.parse_args()

    simparams = Constant("OTHH", "simulation")  # Will later passed as parameter
    simparams._rawdata["starttime"] = args.startdate
    if "enddate" in args:
        simparams._rawdata["endtime"] = args.enddate
    else:
        simparams._rawdata["flightcount"] = args.count

    home = ManagedAirport("OTHH")

    flightboard = Flightboard(home, simparams)
    out = flightboard.generate()

    logger.debug(out)


if __name__ == "__main__":
    main()
