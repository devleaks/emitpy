import logging
from datetime import datetime, timedelta

from emitpy.business import AirportManager, Company, Airline
from emitpy.airport import Airport, XPAirport
from emitpy.aircraft import AircraftType, AircraftPerformance
from emitpy.service import Service, ServiceMove
from emitpy.emit import Emit, Format, LiveTrafficFormatter

from emitpy.parameters import MANAGED_AIRPORT
from emitpy.constants import SERVICE, SERVICE_PHASE

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

    logger.debug("loading managed airport..")

    logger.debug("..loading airport manager..")
    airportManager = AirportManager(icao=MANAGED_AIRPORT["ICAO"])
    airportManager.load()
    # print(airportManager.getAirlineCombo())
    # print(airportManager.getAirrouteCombo("PC"))

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


    logger.debug("loading aircraft..")
    actype = AircraftPerformance.find("A321")
    actype.load()
    logger.debug(f"..done {actype.available}")

    ramp = managed.selectRamp(None)

    # managed.service_roads.print(vertex=False)
    operator = Company(orgId="Airport Operator", classId="Airport Operator", typeId="Airport Operator", name="MATAR")

    logger.debug("creating single service..")
    fs = Service.getService("baggage")
    fuel_service = fs(operator=operator, quantity=125)
    fuel_service.setRamp(ramp)
    fuel_service.setAircraftType(actype)
    fuel_vehicle = airportManager.selectServiceVehicle(operator=operator, service=fuel_service, model="train")
    fuel_vehicle.setICAO24("abcdef")
    fuel_depot = managed.selectRandomServiceDepot(SERVICE.FUEL.value)
    fuel_vehicle.setPosition(fuel_depot)
    fuel_rest = managed.selectRandomServiceRestArea(SERVICE.FUEL.value)
    fuel_vehicle.setNextPosition(fuel_rest)

    logger.debug(".. moving ..")

    fsm = ServiceMove(fuel_service, managed)
    fsm.move_loop()
    fsm.save()

    logger.debug(".. emission positions ..")

    se = Emit(fsm)
    se.emit()
    se.save()

    logger.debug(".. scheduling broadcast ..")

    print(se.getMarkList())

    service_duration = fuel_service.duration()
    se.pause(SERVICE_PHASE.SERVICE_START.value, service_duration)
    logger.debug(f".. service duration {service_duration} ..")

    se.schedule(SERVICE_PHASE.SERVICE_START.value, datetime.now() + timedelta(minutes=5))

    logger.debug(".. broadcasting position ..")

    b = Format(se, LiveTrafficFormatter)
    b.format()
    b.save()

    logger.debug("..done")

main()
