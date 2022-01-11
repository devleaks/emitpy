import logging
from entity.airspace import XPAirspace

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("Airspace")

def main():

    a = XPAirspace()
    logger.debug("loading..")
    a.load()
    logger.debug("..done")

main()
