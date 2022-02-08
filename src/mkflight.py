import logging

from entity.business import Airline
from entity.airspace import XPAirspace
from entity.airport import Airport, XPAirport
from entity.aircraft import AircraftType, AircraftPerformance, Aircraft
from entity.flight import Arrival, Departure, Movement
from entity.business import AirportManager
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

    logger.debug("loading airlines..")
    Airline.loadAll()
    logger.debug("..done")

    logger.debug("loading aircrafts..")
    AircraftType.loadAll()
    AircraftPerformance.loadAll()
    logger.debug("..done")

    logger.debug("..done")

    logger.debug("loading managed airport..")

    logger.debug("..loading airport manager..")
    airportManager = AirportManager(icao=MANAGED_AIRPORT["ICAO"])
    airportManager.load()

    logger.debug("..loading managed airport..")
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
    ret = managed.load()
    if not ret[0]:
        print("Airport not loaded")
    managed.setAirspace(airspace)

    logger.debug("..done")

    # Prepare airport for each movement
    metar = "OTHH 041200Z 26113KT 9999 FEW030 20/08 Q1017 NOSIG"
    managed.setMETAR(metar=metar)  # calls prepareRunways()

    # Add pure commercial stuff
    qr = Airline.findIATA(iata="QR")
    airportManager.hub(managed, qr)

    # Create a pair of flights
    airline = qr
    # other_airport = Airport.find("VOCL")
    (airline, other_airport) = airportManager.getRandomAirport(airline=airline)
    reqrange = managed.miles(other_airport)

    logger.debug("loading aircraft..")
    acperf = AircraftPerformance.findAircraft(reqrange=reqrange)
    reqfl = acperf.FLFor(reqrange)

    logger.info("***** Flying from/to %s (%dkm)(%s, %s) with %s (%s, %s)" % (other_airport["properties"]["city"], reqrange, other_airport.iata, other_airport.icao, airline.orgId, airline.iata, airline.icao))
    logger.info("***** range is %dkm, aircraft will be %s at FL%d" % (reqrange, acperf.typeId, reqfl))

    aircraft = Aircraft(registration="A7-PMA", actype=acperf, operator=airline)
    logger.debug("..done")

    logger.debug("creating arrival..")
    arr = Arrival(operator=airline, number="4L", scheduled="2022-01-18T14:00:00+02:00", managedAirport=managed, origin=other_airport, aircraft=aircraft)
    arr.setFL(reqfl)
    ramp = managed.getRamp(arr)  # Plane won't get towed
    arr.setRamp(ramp)
    gate = "C99"
    if ramp[0] in "A,B,C,D,E".split(",") and len(ramp) < 5:  # does now work for "Cargo Ramp F5" ;-)
        gate = ramp
    arr.setGate(gate)
    logger.debug("..planning..")
    arr.plan()
    logger.debug("..done")

    logger.debug("creating departure..")
    dep = Departure(operator=airline, number="3", scheduled="2022-01-18T16:00:00+02:00", managedAirport=managed, destination=other_airport, aircraft=aircraft)
    dep.setFL(reqfl)
    dep.setRamp(ramp)
    dep.setGate(gate)
    logger.debug("..planning..")
    dep.plan()
    logger.debug("..done")

    logger.debug("flying..")
    am = Movement.create(arr, managed)
    am.make()

    # metar may change between the two
    managed.setMETAR(metar=metar)  # calls prepareRunways()
    dm = Movement.create(dep, managed)
    dm.make()

    logger.debug("..done")

main()

