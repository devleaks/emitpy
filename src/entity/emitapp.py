import logging
import json

from datetime import datetime, timedelta

from entity.managedairport import ManagedAirport
from entity.business import Airline, Company
from entity.aircraft import AircraftType, AircraftPerformance, Aircraft
from entity.flight import Arrival, Departure, ArrivalMove, DepartureMove
from entity.service import Service, ServiceMove
from entity.emit import Emit, ReEmit,ADSB, LiveTraffic, Format, FormatToRedis
from entity.business import AirportManager
from entity.constants import SERVICE, SERVICE_PHASE, FLIGHT_PHASE, REDIS_QUEUE
from entity.airport import Airport, AirportBase
from entity.airspace import Metar
from entity.utils import NAUTICAL_MILE

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("EmitApp")


class ErrorInfo:

    def __init__(self, errno: int, errmsg: str, data):
        self.ei = {
            "errno": errno,
            "errmsg": errmsg,
            "data": data
        }

    def __str__(self):
        return json.dumps(self.ei)


class EmitApp(ManagedAirport):

    def __init__(self, airport):
        ManagedAirport.__init__(self, airport)
        self.init()


    def do_service(self, operator, service, quantity, ramp, aircraft, vehicle_ident, vehicle_icao24, vehicle_model, vehicle_startpos, vehicle_endpos, scheduled):
        logger.debug("loading aircraft..")
        actype = AircraftPerformance.find(aircraft)
        if actype is None:
            return {
                "errno": 510,
                "errmsg": f"EmitApp:do_service: aircraft performance {aircraft} not found",
                "data": None
            }
        actype.load()
        logger.debug(f"..done {actype.available}")

        operator = Company(orgId="Airport Operator", classId="Airport Operator", typeId="Airport Operator", name="MARTAR")

        logger.debug("creating single service..")
        this_service = Service.getService(service)(operator=operator, quantity=quantity)
        rampval = self.airport.getRamp(ramp)
        if rampval is None:
            return {
                "errno": 511,
                "errmsg": f"EmitApp:do_service: ramp {ramp} not found",
                "data": None
            }
        this_service.setRamp(rampval)
        this_service.setAircraftType(actype)
        this_vehicle = self.airport.manager.selectServiceVehicle(operator=operator, service=this_service, model=vehicle_model)
        if this_vehicle is None:
            return {
                "errno": 512,
                "errmsg": f"EmitApp:do_service: vehicle not found",
                "data": None
            }
        this_vehicle.setICAO24(vehicle_icao24)
        startpos = self.airport.selectServicePOI(vehicle_startpos, service)
        if startpos is None:
            return {
                "errno": 513,
                "errmsg": f"EmitApp:do_service: start position {vehicle_startpos} for {service} not found",
                "data": None
            }
        this_vehicle.setPosition(startpos)
        nextpos = self.airport.selectServicePOI(vehicle_endpos, service)
        if nextpos is None:
            return {
                "errno": 513,
                "errmsg": f"EmitApp:do_service: start position {vehicle_endpos} for {service} not found",
                "data": None
            }
        this_service.setNextPosition(nextpos)

        logger.debug(".. moving ..")
        move = ServiceMove(this_service, self.airport)
        move.move()
        move.save()

        logger.debug(".. emission positions ..")
        emit = Emit(move)
        emit.emit()

        logger.debug(emit.getMarkList())
        service_duration = this_service.serviceDuration()

        logger.debug(f".. service duration {service_duration} ..")
        emit.addToPause(SERVICE_PHASE.SERVICE_START.value, service_duration)
        # will trigger new call to emit.emit() to adjust

        logger.debug(".. scheduling broadcast ..")
        # default is to serve at scheduled time
        logger.debug(f".. {SERVICE_PHASE.SERVICE_START.value} at {scheduled} ..")
        emit.schedule(SERVICE_PHASE.SERVICE_START.value, datetime.fromisoformat(scheduled))
        emit.save()
        emit.saveDB()

        logger.debug(".. broadcasting position ..")
        formatted = FormatToRedis(emit, LiveTraffic)
        formatted.run()
        formatted.save(overwrite=True)
        formatted.enqueue(REDIS_QUEUE.ADSB.value)

        logger.debug("..done")

        return {
            "errno": 0,
            "errmsg": "completed successfully",
            "data": len(emit._emit)
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
        formatted = FormatToRedis(emit, LiveTraffic)
        formatted.run()
        formatted.save()
        formatted.enqueue(REDIS_QUEUE.ADSB.value)
        logger.debug("..done.")

        return {
            "errno": 0,
            "errmsg": "completed successfully",
            "data": len(emit._emit)
        }


    def do_schedule(self, ident, sync, scheduled):
        emit = ReEmit(ident)
        emit.schedule(sync, datetime.fromisoformat(scheduled))

        logger.debug("..broadcasting positions..")
        formatted = FormatToRedis(emit, LiveTraffic)
        formatted.run()
        formatted.save(overwrite=True)
        formatted.enqueue(REDIS_QUEUE.ADSB.value)
        logger.debug("..done.")

        return {
            "errno": 0,
            "errmsg": "completed successfully",
            "data": len(emit._emit)
        }


