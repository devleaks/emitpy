import logging
from entity.business import airportmanager as Airport

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("mkApt")

def main():

    a = Airport(icao="OTHH")
    logger.debug("loading..")
    a.load()
    logger.debug("..done")

main()
