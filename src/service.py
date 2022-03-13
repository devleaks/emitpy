import logging
import json

from datetime import datetime, timedelta

from entity.business import AirportManager, Company, Airline
from entity.airport import Airport, XPAirport
from entity.aircraft import AircraftType, AircraftPerformance
from entity.service import FuelService, ServiceMove
from entity.emit import Emit, BroadcastToFile, LiveTraffic
from entity.geo import getFeatureCollection

from entity.parameters import MANAGED_AIRPORT
from entity.constants import SERVICE, SERVICE_PHASE

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("serviceworker")


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


def do_service(operator, service, quantity, ramp, aircraft, vehicle_ident, vehicle_icao24, vehicle_model, vehicle_startpos, vehicle_endpos, scheduled):
    logger.debug("loading aircraft..")
    actype = AircraftPerformance.find(aircraft)
    actype.load()
    logger.debug(f"..done {actype.available}")

    operator = Company(orgId="Airport Operator", classId="Airport Operator", typeId="Airport Operator", name="MARTAR")

    logger.debug("creating single service..")
    fuel_service = FuelService(operator=operator, quantity=quantity)
    rp = managed.getRamp(ramp)
    print(rp)
    fuel_service.setRamp(rp)
    fuel_service.setAircraftType(actype)
    fuel_vehicle = airportManager.selectServiceVehicle(operator=operator, service=fuel_service, model=vehicle_model)
    fuel_vehicle.setICAO24(vehicle_icao24)
    sp = managed.selectRandomServiceDepot("fuel")
    fuel_vehicle.setPosition(sp)
    np = managed.selectRandomServiceDepot("fuel")
    fuel_service.setNextPosition(np)

    logger.debug(".. moving ..")
    fsm = ServiceMove(fuel_service, managed)
    fsm.move()
    fsm.save()
    logger.debug(".. emission positions ..")
    se = Emit(fsm)
    se.emit()
    se.save()
    logger.debug(".. scheduling broadcast ..")
    logger.debug(se.getMarkList())
    service_duration = fuel_service.serviceDuration()
    se.pause(SERVICE_PHASE.SERVICE_START.value, service_duration)
    logger.debug(f".. service duration {service_duration} ..")
    se.schedule(SERVICE_PHASE.SERVICE_START.value, datetime.fromisoformat(scheduled))
    logger.debug(".. broadcasting position ..")
    b = BroadcastToFile(se, datetime.fromisoformat(scheduled), LiveTraffic)
    b.run()
    logger.debug("..done")
    return b.broadcast
