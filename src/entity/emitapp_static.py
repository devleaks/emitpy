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
from entity.parameters import MANAGED_AIRPORT as AIRPORT_DEFINITION
from entity.constants import SERVICE, SERVICE_PHASE, FLIGHT_PHASE
from entity.utils import NAUTICAL_MILE

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("EmitApp")


class EmitApp:

    AIRPORT = None

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
        manager = AirportManager(icao=AIRPORT_DEFINITION["ICAO"])
        manager.load()

        logger.debug("..loading managed airport..")
        EmitApp.AIRPORT = XPAirport(
            icao=AIRPORT_DEFINITION["ICAO"],
            iata=AIRPORT_DEFINITION["IATA"],
            name=AIRPORT_DEFINITION["name"],
            city=AIRPORT_DEFINITION["city"],
            country=AIRPORT_DEFINITION["country"],
            region=AIRPORT_DEFINITION["regionName"],
            lat=AIRPORT_DEFINITION["lat"],
            lon=AIRPORT_DEFINITION["lon"],
            alt=AIRPORT_DEFINITION["elevation"])
        ret = EmitApp.AIRPORT.load()
        if not ret[0]:
            print("Managed airport not loaded")

        EmitApp.AIRPORT.setAirspace(airspace)
        EmitApp.AIRPORT.setManager(manager)
        logger.debug("..done")

        logger.debug("..collecting METAR..")
        # Prepare airport for each movement
        metar = Metar(icao=AIRPORT_DEFINITION["ICAO"])
        EmitApp.AIRPORT.setMETAR(metar=metar)  # calls prepareRunways()

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
        rp = EmitApp.AIRPORT.getRamp(ramp)
        fuel_service.setRamp(rp)
        fuel_service.setAircraftType(actype)
        fuel_vehicle = EmitApp.AIRPORT.manager.selectServiceVehicle(operator=operator, service=fuel_service, model=vehicle_model)
        fuel_vehicle.setICAO24(vehicle_icao24)
        sp = EmitApp.AIRPORT.selectRandomServiceDepot("fuel")
        fuel_vehicle.setPosition(sp)
        np = EmitApp.AIRPORT.selectRandomServiceDepot("fuel")
        fuel_service.setNextPosition(np)

        logger.debug(".. moving ..")
        fsm = ServiceMove(fuel_service, EmitApp.AIRPORT)
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
        aptrange = EmitApp.AIRPORT.miles(remote_apt)

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

        logger.debug("..collecting metar..")
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
                    remote_aptgetProp("city"), aptrange/NAUTICAL_MILE, remote_apt.iata, AIRPORT_DEFINITION["IATA"],
                    acperf.typeId, reqfl))
        logger.debug("*" * 90)

        logger.debug("creating flight..")
        flight = None
        if move == "arrival":
            flight = Arrival(operator=airline, number=flightnumber, scheduled=scheduled, managedAirport=EmitApp.AIRPORT, origin=remote_apt, aircraft=aircraft)
        else:
            flight = Departure(operator=airline, number=flightnumber, scheduled=scheduled, managedAirport=EmitApp.AIRPORT, destination=destination_apt, aircraft=aircraft)
        flight.setFL(reqfl)
        ramp = EmitApp.AIRPORT.selectRamp(flight)  # Aircraft won't get towed
        flight.setRamp(ramp)
        # gate = "C99"
        # ramp_name = ramp.getProp("name")
        # if ramp_name[0] in "A,B,C,D,E".split(",") and len(ramp) < 5:  # does now work for "Cargo Ramp F5" ;-)
        #     gate = ramp_name
        # flight.setGate(gate)

        logger.debug("..planning..")
        flight.plan()

        logger.debug("..flying..")
        move = None
        if move == "arrival":
            move = ArrivalMove(flight, EmitApp.AIRPORT)
            sync = FLIGHT_PHASE.TOUCH_DOWN.value
        else:
            move = DepartureMove(flight, EmitApp.AIRPORT)
            sync = FLIGHT_PHASE.TAKE_OFF.value
        move.move()
        # move.save()

        logger.debug("..emission positions..")
        emit = Emit(move)
        emit.emit(30)
        # emit.save()
        logger.debug("..synchronizing..")
        logger.debug(emit.getMarkList())
        emit.schedule(sync, datetime.fromisoformat(scheduled))

        logger.debug("..broadcasting positions..")
        broadcast = BroadcastToFile(emit, datetime.fromisoformat(scheduled), ADSB)
        broadcast.run()
        broadcast.saveDB()
        logger.debug("..done.")

        return len(broadcast.broadcast)
