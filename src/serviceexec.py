import logging
import json

from datetime import datetime, timedelta

from entity.airspace import XPAirspace, Metar
from entity.business import Airline, Company
from entity.aircraft import AircraftType, AircraftPerformance, Aircraft
from entity.flight import Arrival, Departure, ArrivalMove, DepartureMove
from entity.airport import Airport, AirportBase, XPAirport
from entity.service import FuelService, ServiceMove
from entity.emit import Emit, BroadcastToFile, ADSB, LiveTraffic
from entity.business import AirportManager
from entity.parameters import MANAGED_AIRPORT
from entity.constants import SERVICE, SERVICE_PHASE, FLIGHT_PHASE
from entity.utils import NAUTICAL_MILE

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("serviceexec")


class DoService:

    MANAGED = None
    AIRPORTMANAGER = None

    def init():
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

        logger.debug("loading managed airport..")

        logger.debug("..loading airport manager..")
        DoService.AIRPORTMANAGER = AirportManager(icao=MANAGED_AIRPORT["ICAO"])
        DoService.AIRPORTMANAGER.load()

        logger.debug("..loading managed airport..")
        DoService.MANAGED = XPAirport(
            icao=MANAGED_AIRPORT["ICAO"],
            iata=MANAGED_AIRPORT["IATA"],
            name=MANAGED_AIRPORT["name"],
            city=MANAGED_AIRPORT["city"],
            country=MANAGED_AIRPORT["country"],
            region=MANAGED_AIRPORT["regionName"],
            lat=MANAGED_AIRPORT["lat"],
            lon=MANAGED_AIRPORT["lon"],
            alt=MANAGED_AIRPORT["elevation"])
        ret = DoService.MANAGED.load()
        if not ret[0]:
            print("Managed airport not loaded")
        DoService.MANAGED.setAirspace(airspace)
        logger.debug("..done")

        logger.debug("..collecting METAR..")
        # Prepare airport for each movement
        metar = Metar(icao=MANAGED_AIRPORT["ICAO"])
        DoService.MANAGED.setMETAR(metar=metar)  # calls prepareRunways()

        logger.debug("..done")


    @staticmethod
    def do_service(operator, service, quantity, ramp, aircraft, vehicle_ident, vehicle_icao24, vehicle_model, vehicle_startpos, vehicle_endpos, scheduled):
        logger.debug("loading aircraft..")
        actype = AircraftPerformance.find(aircraft)
        actype.load()
        logger.debug(f"..done {actype.available}")

        operator = Company(orgId="Airport Operator", classId="Airport Operator", typeId="Airport Operator", name="MARTAR")

        logger.debug("creating single service..")
        fuel_service = FuelService(operator=operator, quantity=quantity)
        rp = DoService.MANAGED.getRamp(ramp)
        fuel_service.setRamp(rp)
        fuel_service.setAircraftType(actype)
        fuel_vehicle = DoService.AIRPORTMANAGER.selectServiceVehicle(operator=operator, service=fuel_service, model=vehicle_model)
        fuel_vehicle.setICAO24(vehicle_icao24)
        sp = DoService.MANAGED.selectRandomServiceDepot("fuel")
        fuel_vehicle.setPosition(sp)
        np = DoService.MANAGED.selectRandomServiceDepot("fuel")
        fuel_service.setNextPosition(np)

        logger.debug(".. moving ..")
        fsm = ServiceMove(fuel_service, DoService.MANAGED)
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
        broadcast = BroadcastToFile(se, datetime.fromisoformat(scheduled), LiveTraffic)
        broadcast.run()
        logger.debug("..done")
        return len(broadcast.broadcast)


    @staticmethod
    def do_flight(airline, flightnumber, scheduled, apt, move, actype, ramp, icao24, acreg, runway):
        # Add pure commercial stuff
        airline = Airline.find(airline)
        remote_apt = Airport.find(apt)
        aptrange = DoService.MANAGED.miles(remote_apt)

        logger.debug("loading other airport..")
        remote_apt = AirportBase(icao=remote_apt.icao,
                                 iata=remote_apt.iata,
                                 name=remote_apt["properties"]["name"],
                                 city=remote_apt["properties"]["city"],
                                 country=remote_apt["properties"]["country"],
                                 region=remote_apt.region,
                                 lat=remote_apt["geometry"]["coordinates"][1],
                                 lon=remote_apt["geometry"]["coordinates"][0],
                                 alt=remote_apt["geometry"]["coordinates"][2] if len(remote_apt["geometry"]["coordinates"]) > 2 else None)
        ret = remote_apt.load()
        if not ret[0]:
            print(f"other airport not loaded: {ret}")

        logger.debug("..collecting METAR..")
        origin_metar = Metar(icao=remote_apt.icao)
        remote_apt.setMETAR(metar=origin_metar)  # calls prepareRunways()
        logger.debug("..done")

        logger.debug("loading aircraft..")
        acperf = AircraftPerformance.find(icao=actype)
        reqfl = acperf.FLFor(aptrange)
        aircraft = Aircraft(registration=acreg, icao24= icao24, actype=acperf, operator=airline)
        logger.debug("..done")

        logger.debug("*" * 90)
        logger.info("*** (%s, %dnm) %s-%s AC %s at FL%d" % (
                    remote_apt["properties"]["city"], aptrange/NAUTICAL_MILE, remote_apt.iata, MANAGED_AIRPORT["IATA"],
                    acperf.typeId, reqfl))
        logger.debug("*" * 90)

        logger.debug("creating flight..")
        flight = None
        if move == "arrival":
            flight = Arrival(operator=airline, number=flightnumber, scheduled=scheduled, managedAirport=DoService.MANAGED, origin=remote_apt, aircraft=aircraft)
        else:
            flight = Departure(operator=airline, number=flightnumber, scheduled=scheduled, managedAirport=DoService.MANAGED, destination=destination_apt, aircraft=aircraft)
        flight.setFL(reqfl)
        ramp = DoService.MANAGED.selectRamp(flight)  # Aircraft won't get towed
        flight.setRamp(ramp)
        gate = "C99"
        ramp_name = ramp.getProp("name")
        if ramp_name[0] in "A,B,C,D,E".split(",") and len(ramp) < 5:  # does now work for "Cargo Ramp F5" ;-)
            gate = ramp_name
        flight.setGate(gate)

        logger.debug("..planning..")
        flight.plan()

        logger.debug("..flying..")
        move = None
        if move == "arrival":
            move = ArrivalMove(flight, DoService.MANAGED)
        else:
            move = DepartureMove(flight, DoService.MANAGED)
        move.move()
        move.save()

        logger.debug("..emission positions..")
        emit = Emit(move)
        emit.emit(30)
        emit.save()
        logger.debug("..pausing/delay test..")
        logger.debug(emit.getMarkList())
        emit.schedule(FLIGHT_PHASE.TOUCH_DOWN.value, datetime.fromisoformat(scheduled))
        emit.pause(FLIGHT_PHASE.TOUCH_DOWN.value, 300)

        logger.debug("..broadcasting positions..")
        broadcast = BroadcastToFile(emit, datetime.fromisoformat(scheduled), ADSB)
        broadcast.run()
        logger.debug("..done.")

        return len(broadcast.broadcast)
