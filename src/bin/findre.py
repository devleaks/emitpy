import sys

sys.path.append("..")

import logging
from emitpy.airport import XPAirport

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("mkApt")

from emitpy.constants import FEATPROP
from emitpy.parameters import MANAGED_AIRPORT_ICAO


def main():
    this_airport = XPAirport.findICAO(MANAGED_AIRPORT_ICAO)
    apt = XPAirport(
        icao=this_airport.icao,
        iata=this_airport.iata,
        name=this_airport.display_name,
        city=this_airport.getProp(FEATPROP.CITY),
        country=this_airport.getProp(FEATPROP.COUNTRY),
        region=this_airport.region,
        lat=this_airport.lat(),
        lon=this_airport.lon(),
        alt=this_airport.altitude(),
    )
    logger.debug("loading airport..")
    apt.load()
    logger.debug("..done")


main()
