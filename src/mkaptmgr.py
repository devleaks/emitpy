import logging
from entity.business import AirportManager

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("mkApt")

from entity.parameters import MANAGED_AIRPORT

def main():

    a = AirportManager(icao=MANAGED_AIRPORT["ICAO"])
    logger.debug("loading..")
    print(a.load())
    logger.debug("..done")

main()
