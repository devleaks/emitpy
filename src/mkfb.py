"""
Make a random flight board from startdate to enddate.
Usage:
    mkfb -s "20210505T10:06:23+02:00" -e "20210505T18:00:00+02:00"

"""
import argparse
import logging

logging.basicConfig(level=logging.DEBUG)  # filename=('mkfb.log')

logger = logging.getLogger("mkfb")

from entity import Flightboard
from entity import ManagedAirport
from entity import Constant


def main():
    parser = argparse.ArgumentParser(description="Generate flight board.")
    parser.add_argument("startdate", type=str, help="start date for flightboard")
    parser.add_argument("enddate", type=str, help="end date for flightboard")
    args = parser.parse_args()


    simparams = Constant("OTHH", "simulation")  # Will later passed as parameter
    simparams._rawdata["starttime"] = args.startdate
    simparams._rawdata["endtime"] = args.enddate

    home = ManagedAirport("OTHH")

    flightboard = Flightboard(home, simparams)
    out = flightboard.generate()

    logger.debug(out)


if __name__ == "__main__":
    main()
