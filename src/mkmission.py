import logging
import random
from datetime import datetime, timedelta

from emitpy.business import AirportManager, Company
from emitpy.airport import Airport, XPAirport
from emitpy.service import Mission, MissionMove
from emitpy.emit import Emit, Format, LiveTrafficFormatter
from emitpy.service.servicevehicle import AirportSecurity

from emitpy.parameters import MANAGED_AIRPORT
from emitpy.constants import SERVICE, MISSION_PHASE

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("mkMission")


def main():

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

    logger.debug("creating mission..")
    # managed.service_roads.print(vertex=False)
    operator = Company(orgId="Airport Security", classId="Airport Operator", typeId="Airport Operator", name="SECURE")
    mission = Mission(operator=operator, checkpoints=[])
    mission_vehicle = AirportSecurity(operator=operator, registration="JB007")
    mission_vehicle.setICAO24("abcdef")
    mission.setVehicle(mission_vehicle)

    fuel_depot = managed.selectRandomServiceDepot(SERVICE.FUEL.value)
    mission_vehicle.setPosition(fuel_depot)
    catering_depot = managed.selectRandomServiceDepot(SERVICE.CATERING.value)
    mission_vehicle.setNextPosition(catering_depot)

    cp_list = ['checkpoint:0', 'checkpoint:1', 'checkpoint:2', 'checkpoint:3', 'checkpoint:4', 'checkpoint:5',
               'checkpoint:6', 'checkpoint:7', 'checkpoint:8', 'checkpoint:9', 'checkpoint:10', 'checkpoint:11',
               'checkpoint:12', 'checkpoint:13', 'checkpoint:14', 'checkpoint:15', 'checkpoint:16', 'checkpoint:17',
               'checkpoint:18', 'checkpoint:19', 'checkpoint:20', 'checkpoint:21', 'checkpoint:22', 'checkpoint:23',
               'checkpoint:24', 'checkpoint:25', 'checkpoint:26', 'checkpoint:27', 'checkpoint:28', 'checkpoint:29',
               'checkpoint:30', 'checkpoint:31', 'checkpoint:32', 'checkpoint:33', 'checkpoint:34', 'checkpoint:35',
               'checkpoint:36', 'checkpoint:37', 'checkpoint:38']
    for i in range(3):
        cp = random.choice(cp_list)
        mission.addCheckpoint(cp)
        logger.debug(f"..adding checkpoint {cp}..")
        cp_list.remove(cp)

    # logger.debug("..running..")

    logger.debug(".. moving ..")

    mm = MissionMove(mission, managed)
    mm.move()
    mm.save()

    logger.debug(".. emission positions ..")

    me = Emit(mm)
    me.emit()
    me.save()

    logger.debug(".. scheduling broadcast ..")

    print(me.getMarkList())

    me.schedule(MISSION_PHASE.START.value, datetime.now() + timedelta(minutes=5))

    logger.debug(".. broadcasting position ..")

    b = Format(me, LiveTrafficFormatter)
    b.format()
    b.save()

    logger.debug("..done")

main()
