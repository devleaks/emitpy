import logging
from emitpy.business import AirportManager, Airline, Company
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

    operator = Company(orgId="Airport Operator", classId="Airport Operator", typeId="Airport Operator", name="MATAR")
    a = AirportManager(icao=MANAGED_AIRPORT["ICAO"], operator=operator)
    logger.debug("loading..")
    a.load()
    logger.debug("..done")

main()
