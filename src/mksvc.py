import logging
from datetime import datetime

from entity.business import Airline, AirportManager, Company
from entity.airport import Airport, XPAirport
from entity.aircraft import AircraftType, AircraftPerformance, Aircraft
from entity.flight import Arrival, Departure

from entity.service import FuelService, ServiceMove
from entity.emit import Emit

from entity.parameters import MANAGED_AIRPORT
from entity.constants import SERVICE

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("mkService")


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
    logger.debug("..done")

    airline = Airline.findIATA(iata="QR")

    (airline, other_airport) = airportManager.selectRandomAirroute(airline=airline)
    reqrange = managed.miles(other_airport)


    ramp = managed.getRamp(None)

    logger.debug("loading aircraft..")
    acperf = AircraftPerformance.findAircraft(reqrange=reqrange)
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
    gate = "C99"
    ramp_name = ramp.getProp("name")
    if ramp_name[0] in "A,B,C,D,E".split(",") and len(ramp) < 5:  # does now work for "Cargo Ramp F5" ;-)
        gate = ramp_name
    arr.setGate(gate)
    logger.debug("..done")

    logger.debug("creating departure..")
    dep = Departure(operator=airline, number="321", scheduled="2022-01-18T16:00:00+02:00", managedAirport=managed, destination=other_airport, aircraft=aircraft, linked_flight=arr)
    dep.setFL(reqfl)
    dep.setRamp(ramp)
    dep.setGate(gate)
    logger.debug("..done")

    # managed.service_roads.print(vertex=False)
    operator = Company(orgId="Airport Operator", classId="Airport Operator", typeId="Airport Operator", name="MARTAR")

    logger.debug("creating single service..")
    fuel_service = FuelService(operator=operator, quantity=24)
    fuel_service.setRamp(ramp)
    fuel_service.setFlight(dep)
    fuel_vehicle = airportManager.selectServiceVehicle(operator=operator, service=fuel_service, model="pump")
    fuel_depot = managed.selectRandomServiceDepot(SERVICE.FUEL.value)
    fuel_vehicle.setPosition(fuel_depot)
    fuel_rest = managed.selectRandomServiceRestArea(SERVICE.FUEL.value)
    fuel_service.setNextPosition(fuel_rest)

    logger.debug(".. moving ..")

    fsm = ServiceMove(fuel_service, managed)
    fsm.move()
    fsm.save()

    logger.debug(".. bradcasting positions ..")

    se = Emit(fsm)
    se.emit()
    se.save()

    logger.debug("..done")

main()
