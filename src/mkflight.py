import logging

from entity.business import Airline
from entity.airspace import XPAirspace
from entity.airport import Airport, XPAirport
from entity.aircraft import AircraftType, AircraftPerformance, Aircraft
from entity.flight import Arrival, Departure
from entity.flight import ArrivalPath, DeparturePath
from entity.parameters import MANAGED_AIRPORT

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("mkFlight")


def main():

    airspace = XPAirspace()
    logger.debug("loading airspace..")
    airspace.load()
    logger.debug("..done")


    logger.debug("loading airport..")
    Airport.loadAll()
    logger.debug("..done")

    other_airport = Airport.find(icao="OMDB")

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
    logger.debug("loading airport..")
    managed.load()
    managed.setAirspace(airspace)
    logger.debug("..done")

    logger.debug("loading airlines..")
    Airline.loadAll()
    airline = Airline.find(icao="QTR")
    logger.debug("..done")

    logger.debug("loading aircrafts..")
    AircraftType.loadAll()
    logger.debug("..done")
    logger.debug("loading aircraft..")
    actype = AircraftType.find("A320")
    acperf = AircraftPerformance(actype.orgId, actype.classId, actype.typeId, actype.name)
    acperf.loadPerformance()

    aircraft = Aircraft(registration="A7-PMA", actype=acperf, operator=airline)
    logger.debug("..done")

    logger.debug("creating arrival..")

    arr = Arrival(operator=airline, number="4", scheduled="2022-01-18T14:00:00+02:00", managedAirport=managed, origin=other_airport, aircraft=aircraft)

    ramp = managed.getRamp(arr)  # "A 7"  # Plane won't get towed
    arr.setRamp(ramp)

    gate = "C99"
    if ramp[0] in "A,B,C,D,E".split(",") and len(ramp) < 5:  # does now work for "Cargo Ramp F5" ;-)
        gate = ramp
    arr.setGate(gate)

    logger.debug("..planning..")
    arr.plan()
    ap = ArrivalPath(arr)
    pa = ap.mkPath()
    logger.debug("..done")


    logger.debug("creating departure..")
    dep = Departure(operator=airline, number="3", scheduled="2022-01-18T16:00:00+02:00", managedAirport=managed, destination=other_airport, aircraft=aircraft)
    dep.setRamp(ramp)
    dep.setGate(gate)

    logger.debug("..planning..")
    dep.plan()
    dp = DeparturePath(dep)
    pd = dp.mkPath()
    logger.debug("..done")


    logger.debug("flying..")
    arr.fly()
    dep.fly()
    logger.debug("..done")

main()
