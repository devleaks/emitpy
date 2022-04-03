import logging
from emitpy.business import AirportManager, Airline
from emitpy.airport import Airport

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("mkAirportManager")

from emitpy.parameters import MANAGED_AIRPORT

def main():

    logger.debug("loading airport..")
    Airport.loadAll()
    logger.debug("..done")

    logger.debug("loading airlines..")
    Airline.loadAll()
    logger.debug("..done")


    a = AirportManager(icao=MANAGED_AIRPORT["ICAO"])
    logger.debug("loading..")
    a.load()
    logger.debug("..done")

main()
