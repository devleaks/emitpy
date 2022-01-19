import logging

from entity.business import Airline
from entity.airport import Airport, XPAirport
from entity.aircraft import AircraftType, AircraftPerformance, Aircraft
from entity.flight import Arrival, Departure

from entity.parameters import MANAGED_AIRPORT

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("mkFlight")


def main():

    logger.debug("loading airport..")
    Airport.loadAll()
    airport = Airport.find(icao="OBBI")
    managed = XPAirport(
        icao=MANAGED_AIRPORT["ICAO"],
        iata=MANAGED_AIRPORT["IATA"],
        name=MANAGED_AIRPORT["name"],
        city=MANAGED_AIRPORT["city"],
        country=MANAGED_AIRPORT["country"],
        region=MANAGED_AIRPORT["regionName"],
        lat=MANAGED_AIRPORT["lat"],
        lon=MANAGED_AIRPORT["lon"],
        alt=MANAGED_AIRPORT["elevation"])
    managed.load()
    logger.debug("..done")

    logger.debug("loading airlines..")
    Airline.loadAll()
    airline = Airline.find(icao="QTR")
    logger.debug("..done")

    logger.debug("loading aircraft..")
    AircraftType.loadAll()
    actype = AircraftType.find("A320")
    acperf = AircraftPerformance(actype.orgId, actype.classId, actype.typeId, actype.name)
    acperf.loadPerformance()

    aircraft = Aircraft(registration="A7-PMA", actype=acperf, operator=airline)
    logger.debug("..done")

    d = Departure(operator=airline, number="3", scheduled="2022-01-18T16:00:00+02:00", managedAirport=managed, destination=airport, aircraft=aircraft)
    a = Arrival(operator=airline, number="4", scheduled="2022-01-18T14:00:00+02:00", managedAirport=managed, origin=airport, aircraft=aircraft)

    logger.debug("planning..")
    a.plan()
    d.plan()
    logger.debug("..done")

    logger.debug("flying..")
    a.fly()
    d.fly()
    logger.debug("..done")

main()
