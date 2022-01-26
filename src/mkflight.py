import logging

from entity.business import Airline
from entity.airspace import XPAirspace
from entity.airport import Airport, XPAirport
from entity.aircraft import AircraftType, AircraftPerformance, Aircraft
from entity.flight import Flight, Arrival, Departure
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

    ramp = "A 7"  # Plane won't get towed
    gate = "A7"

    logger.debug("creating arrival..")

    arr = Arrival(operator=airline, number="4", scheduled="2022-01-18T14:00:00+02:00", managedAirport=managed, origin=other_airport, aircraft=aircraft)
    arr.setRamp(ramp)
    arr.setGate(gate)

    logger.debug("..planning..")
    arrpts = ["ENRT"]

    rwy = managed.getRunway(arr)
    print("RWY> ", rwy.name)
    star = managed.getProcedure(arr, rwy)
    print("STAR> ", star.name)
    ret = managed.procedures.getRoute(star, airspace)
    arrpts = arrpts + ret

    apprch = managed.getApproach(star, rwy)
    print("APPCH> ", apprch.name)
    ret = managed.procedures.getRoute(apprch, airspace)
    arrpts = arrpts + ret

    arrpts = arrpts + [rwy.name]
    logger.debug("mkFlight: arrival: %s", arrpts)

    ap = ArrivalPath(arr)
    pa = ap.mkPath()
    arr.plan()

    logger.debug("..done")


    logger.debug("creating departure..")
    dep = Departure(operator=airline, number="3", scheduled="2022-01-18T16:00:00+02:00", managedAirport=managed, destination=other_airport, aircraft=aircraft)
    dep.setRamp(ramp)
    dep.setGate(gate)

    logger.debug("..planning..")

    rwy = managed.getRunway(dep)
    print("RWY> ", rwy.name)
    deppts = [rwy.name]

    sid = managed.getProcedure(dep, rwy)
    print("SID> ", sid.name)
    ret = managed.procedures.getRoute(sid, airspace)
    deppts = deppts + ret

    deppts = deppts + ["ENRT"]
    logger.debug("mkFlight: departure: %s", deppts)
    dep.plan()
    dp = DeparturePath(a)
    pd = dp.mkPath()
    logger.debug("..done")


    logger.debug("flying..")
    a.fly()
    d.fly()
    logger.debug("..done")

main()
