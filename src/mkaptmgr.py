import logging
from entity.business import AirportManager, Airline
from entity.airport import Airport

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("mkAirportManager")

from entity.parameters import MANAGED_AIRPORT

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
