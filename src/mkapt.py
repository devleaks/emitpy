import logging
from entity.business import AirportManager
from entity.airspace import XPAirspace
from entity.airport import XPAirport, GeoJSONAirport, OSMAirport
from entity.flight import Arrival, Departure

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("mkApt")

from entity.parameters import MANAGED_AIRPORT

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

    rwy = apt.getRunway("")
    print("RWY> ", rwy)
    r = apt.getProcedure("", rwy)
    print("SID> ", r)
    r = apt.procedures.getRoute("STAR", "AFNA1C", aspc)
    print("STAR> ", r)
    r = apt.procedures.getRoute("APPCH", "D16L", aspc)
    print("APPCH> ", r)

    r = apt.getRunway("")
    print("RWY> ", r)
    r = apt.procedures.getRoute("SID", "ALSE1C", aspc)
    print("SID>", r)
main()
