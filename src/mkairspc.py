import logging
from entity.airspace import XPAirspace

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("Airspace")

def main():

    a = XPAirspace()
    a.load()

    logger.debug("finding route..")
    a.mkRoute("OMDB", "OTHH")
    logger.debug("..done")

main()
