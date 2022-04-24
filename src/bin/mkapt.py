import logging
from emitpy.business import AirportManager
from emitpy.airspace import XPAirspace
from emitpy.airport import XPAirport, GeoJSONAirport, OSMAirport
from emitpy.flight import Arrival, Departure

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("mkApt")

from emitpy.parameters import MANAGED_AIRPORT

def main():

    aspc = XPAirspace()
    logger.debug("loading airspace..")
    aspc.load()
    logger.debug("..done")

    apt = XPAirport(
        icao=MANAGED_AIRPORT["ICAO"],
        iata=MANAGED_AIRPORT["IATA"],
        name=MANAGED_AIRPORT["name"],
        city=MANAGED_AIRPORT["city"],
        country=MANAGED_AIRPORT["country"],
        region=MANAGED_AIRPORT["regionName"],
        lat=MANAGED_AIRPORT["lat"],
        lon=MANAGED_AIRPORT["lon"],
        alt=MANAGED_AIRPORT["elevation"])
    logger.debug("loading airport..")
    apt.load()
    logger.debug("..done")

    apt.setAirspace(aspc)
    print("airspace and managed airport ready")
main()
