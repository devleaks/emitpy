import logging
from datetime import datetime

from emitpy.business import Airline, AirportManager, Company
from emitpy.airport import Airport, XPAirport
from emitpy.aircraft import AircraftType, AircraftPerformance, Aircraft
from emitpy.flight import Arrival, Departure

from emitpy.service import Turnaround

from emitpy.parameters import MANAGED_AIRPORT

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("mkFlightService")


def main():

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
        print("Managed airport not loaded")

    managed.setManager(airportManager)

    logger.debug("..done")

    airline = Airline.findIATA(iata="QR")

    (airline, other_airport) = airportManager.selectRandomAirroute(airline=airline)
    reqrange = managed.miles(other_airport)


    ramp = managed.getRamp(None)

    logger.debug("loading aircraft..")
    acperf = AircraftPerformance.findAircraftForRange(reqrange=reqrange)
    acperf.load()
    reqfl = acperf.FLFor(reqrange)

    logger.info("FLIGHT ********** From/to %s (%dkm)(%s, %s) with %s (%s, %s)" % (other_airport["properties"]["city"], reqrange, other_airport.iata, other_airport.icao, airline.orgId, airline.iata, airline.icao))
    logger.info("       ********** Range is %dkm, aircraft will be %s at FL%d" % (reqrange, acperf.typeId, reqfl))

    aircraft = Aircraft(registration="A7-PMA", icao24= "a2ec4f", actype=acperf, operator=airline)
    logger.debug("..done")

    logger.debug("creating arrival..")
    arr = Arrival(operator=airline, number="4L", scheduled="2022-01-18T14:00:00+02:00", managedAirport=managed, origin=other_airport, aircraft=aircraft)
    arr.setFL(reqfl)
    ramp = managed.selectRamp(arr)  # Aircraft won't get towed
    arr.setRamp(ramp)
    logger.debug("..done")


    logger.debug("creating departure..")
    dep = Departure(operator=airline, number="3", scheduled="2022-01-18T16:00:00+02:00", managedAirport=managed, destination=other_airport, aircraft=aircraft, linked_flight=arr)
    dep.setFL(reqfl)
    dep.setRamp(ramp)
    logger.debug("..done")

    # managed.service_roads.print(vertex=False)
    operator = Company(orgId="Airport Operator", classId="Airport Operator", typeId="Airport Operator", name="MATAR")

    # logger.debug("creating service..")
    # service_arr = FlightServices(flight=arr, operator=operator)
    # service_arr.setManagedAirport(managed)
    # service_arr.service()

    # service_dep = FlightServices(flight=dep, operator=operator)
    # service_dep.setManagedAirport(managed)
    # service_dep.service()
    #
    turnaround = Turnaround(arrival=arr, departure=dep, operator=operator)
    turnaround.setManagedAirport(managed)
    turnaround.service()
    turnaround.move()
    turnaround.emit(emit_rate=30)
    turnaround.save()

    logger.debug("..done")

main()
