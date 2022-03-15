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
from entity.constants import SERVICE, SERVICE_PHASE, FLIGHT_PHASE
from entity.utils import NAUTICAL_MILE

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("EmitApp")


class EmitApp:


    def __init__(self, airport):
        self._this_airport = airport
        self.airport = None

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
        manager = AirportManager(icao=self._this_airport["ICAO"])
        manager.load()

        logger.debug("..loading managed airport..")
        self.airport = XPAirport(
            icao=airport["ICAO"],
            iata=airport["IATA"],
            name=airport["name"],
            city=airport["city"],
            country=airport["country"],
            region=airport["regionName"],
            lat=airport["lat"],
            lon=airport["lon"],
            alt=airport["elevation"])
        ret = self.airport.load()
        if not ret[0]:
            print("Managed airport not loaded")

        self.airport.setAirspace(airspace)
        self.airport.setManager(manager)
        logger.debug("..done")

        self.update_metar()


    def update_metar(self):
        logger.debug("collecting METAR..")
        # Prepare airport for each movement
        metar = Metar(icao=self._this_airport["ICAO"])
        self.airport.setMETAR(metar=metar)  # calls prepareRunways()
        logger.debug("..done")


    def do_service(self, operator, service, quantity, ramp, aircraft, vehicle_ident, vehicle_icao24, vehicle_model, vehicle_startpos, vehicle_endpos, scheduled):
        logger.debug("loading aircraft..")
        actype = AircraftPerformance.find(aircraft)
        actype.load()
        logger.debug(f"..done {actype.available}")

        operator = Company(orgId="Airport Operator", classId="Airport Operator", typeId="Airport Operator", name="MARTAR")

        logger.debug("creating single service..")
        fuel_service = FuelService(operator=operator, quantity=quantity)
        rp = self.airport.getRamp(ramp)
        fuel_service.setRamp(rp)
        fuel_service.setAircraftType(actype)
        fuel_vehicle = self.airport.manager.selectServiceVehicle(operator=operator, service=fuel_service, model=vehicle_model)
        fuel_vehicle.setICAO24(vehicle_icao24)
        sp = self.airport.selectRandomServiceDepot("fuel")
        fuel_vehicle.setPosition(sp)
        np = self.airport.selectRandomServiceDepot("fuel")
        fuel_service.setNextPosition(np)

        logger.debug(".. moving ..")
        fsm = ServiceMove(fuel_service, self.airport)
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
        return {
            "errno": 0,
            "errmsg": "completed successfully",
            "data": len(broadcast.broadcast)
        }


    def do_flight(self, airline, flightnumber, scheduled, apt, movetype, actype, ramp, icao24, acreg, runway):
        # Add pure commercial stuff
        airline = Airline.find(airline)
        remote_apt = Airport.find(apt)
        aptrange = self.airport.miles(remote_apt)

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
                    remote_apt.getProp("city"), aptrange/NAUTICAL_MILE, remote_apt.iata, self._this_airport["IATA"],
                    acperf.typeId, reqfl))
        logger.debug("*" * 90)

        logger.debug("creating flight..")
        flight = None
        if movetype == "arrival":
            flight = Arrival(operator=airline, number=flightnumber, scheduled=scheduled, managedAirport=self.airport, origin=remote_apt, aircraft=aircraft)
        else:
            flight = Departure(operator=airline, number=flightnumber, scheduled=scheduled, managedAirport=self.airport, destination=destination_apt, aircraft=aircraft)
        flight.setFL(reqfl)
        ramp = self.airport.selectRamp(flight)  # Aircraft won't get towed
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
        if movetype == "arrival":
            move = ArrivalMove(flight, self.airport)
            sync = FLIGHT_PHASE.TOUCH_DOWN.value
        else:
            move = DepartureMove(flight, self.airport)
            sync = FLIGHT_PHASE.TAKE_OFF.value
        move.move()
        move.save()

        logger.debug("..emission positions..")
        emit = Emit(move)
        emit.emit(30)
        emit.save()
        emit.saveDB()
        logger.debug("..synchronizing..")
        logger.debug(emit.getMarkList())
        emit.schedule(sync, datetime.fromisoformat(scheduled))

        logger.debug("..broadcasting positions..")
        start = datetime.fromisoformat(scheduled) - timedelta(seconds=emit.offset)
        broadcast = BroadcastToFile(emit, start, ADSB)
        broadcast.run()
        broadcast.saveDB()
        logger.debug("..done.")

        return {
            "errno": 0,
            "errmsg": "completed successfully",
            "data": len(emit._emit)
        }
