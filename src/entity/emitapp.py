import logging
import json

from datetime import datetime, timedelta

from entity.managedairport import ManagedAirport
from entity.business import Airline, Company
from entity.aircraft import AircraftType, AircraftPerformance, Aircraft
from entity.flight import Arrival, Departure, ArrivalMove, DepartureMove
from entity.service import Service, ServiceMove, ServiceFlight
from entity.emit import Emit, ReEmit, FormatToRedis, LiveTraffic, ADSB
from entity.business import AirportManager
from entity.constants import SERVICE, SERVICE_PHASE, FLIGHT_PHASE, REDIS_QUEUE
from entity.airport import Airport, AirportBase
from entity.airspace import Metar
from entity.utils import NAUTICAL_MILE


logger = logging.getLogger("EmitApp")


class ErrorInfo:

    def __init__(self, errno: int, errmsg: str, data):
        self.errno = errno
        self.errmsg = errmsg
        self.data = data

    def __str__(self):
        return json.dumps({
            "errno": self.errno,
            "errmsg": self.errmsg,
            "data": self.data
        })


SAVE_TO_FILE = False


class EmitApp(ManagedAirport):

    def __init__(self, airport):
        ManagedAirport.__init__(self, airport)
        self.init()


    def do_flight(self, airline, flightnumber, scheduled, apt, movetype, acarr, ramp, icao24, acreg, runway, do_services: bool = False):
        logger.debug("Airline, airport..")
        # Add pure commercial stuff
        airline = Airline.find(airline)
        remote_apt = Airport.find(apt)
        aptrange = self.airport.miles(remote_apt)
        logger.debug("..done")

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
            logger.warning(f"other airport not loaded: {ret}")
            return ret

        logger.debug("..collecting metar..")
        origin_metar = Metar(icao=remote_apt.icao)
        remote_apt.setMETAR(metar=origin_metar)  # calls prepareRunways()
        logger.debug("..done")

        logger.debug("loading aircraft..")
        actype, acsubtype = acarr
        ac = AircraftPerformance.findAircraftByType(actype, acsubtype)
        if ac is None:
            return ErrorInfo(100, f"aircraft performance not found for {actype} or {acsubtype}", None)
        acperf = AircraftPerformance.find(icao=ac)
        if acperf is None:
            return ErrorInfo(101, f"aircraft performance not found for {ac}", None)
        acperf.load()
        reqfl = acperf.FLFor(aptrange)
        aircraft = Aircraft(registration=acreg, icao24= icao24, actype=acperf, operator=airline)
        logger.debug("..done")

        logger.info("*" * 90)
        logger.info("*** (%s, %dnm) %s-%s AC %s at FL%d" % (
                    remote_apt.getProp("city"), aptrange/NAUTICAL_MILE, remote_apt.iata, self._this_airport["IATA"],
                    acperf.typeId, reqfl))
        logger.debug("*" * 90)

        logger.debug("creating flight..")
        flight = None
        if movetype == "arrival":
            flight = Arrival(operator=airline, number=flightnumber, scheduled=scheduled, managedAirport=self.airport, origin=remote_apt, aircraft=aircraft)
        else:
            flight = Departure(operator=airline, number=flightnumber, scheduled=scheduled, managedAirport=self.airport, destination=remote_apt, aircraft=aircraft)
        flight.setFL(reqfl)
        rampval = self.airport.getRamp(ramp)  # Aircraft won't get towed
        if rampval is None:
            logger.warning(f"ramp {ramp} not found, quitting")
            return ErrorInfo(102, f"ramp {ramp} not found", None)

        flight.setRamp(rampval)
        gate = "C99"
        ramp_name = rampval.getProp("name")
        if ramp_name[0] in "A,B,C,D,E".split(",") and len(ramp) < 5:  # does now work for "Cargo Ramp F5" ;-)
            gate = ramp_name
        flight.setGate(gate)

        logger.debug("..planning..")
        flight.plan()

        logger.debug("..flying..")
        move = None
        if movetype == "arrival":
            move = ArrivalMove(flight, self.airport)
            sync = FLIGHT_PHASE.TOUCH_DOWN.value
            svc_sync = FLIGHT_PHASE.ONBLOCK.value
        else:
            move = DepartureMove(flight, self.airport)
            sync = FLIGHT_PHASE.TAKE_OFF.value
            svc_sync = FLIGHT_PHASE.OFFBLOCK.value
        ret = move.move()
        if not ret[0]:
            return ErrorInfo(103, f"problem during move", ret[1])
        # move.save()

        logger.debug("..emission positions..")
        emit = Emit(move)
        ret = emit.emit(30)
        if not ret[0]:
            return ErrorInfo(104, f"problem during emit", ret[1])

        logger.debug("..scheduling..")
        logger.debug(emit.getMarkList())
        schedtime = datetime.fromisoformat(scheduled)
        ret = emit.schedule(sync, schedtime)
        if not ret[0]:
            return ErrorInfo(105, f"problem during schedule", ret[1])

        logger.debug("..saving..")
        if SAVE_TO_FILE:
            ret = emit.save()
            if not ret[0]:
                return ErrorInfo(105, f"problem during schedule", ret[1])
        ret = emit.saveDB()
        if not ret[0]:
            return ErrorInfo(110, f"problem during schedule", ret[1])
        logger.info("SAVED " + ("*" * 84))
        logger.debug("..broadcasting positions..")
        formatted = FormatToRedis(emit, LiveTraffic)
        ret = formatted.format()
        if not ret[0]:
            return ErrorInfo(107, f"problem during formatting", ret[1])
        ret = formatted.save()
        if not ret[0] and ret[1] != "FormatToRedis::save key already exist":
            return ErrorInfo(108, f"problem during formatted output save", ret[1])
        ret = formatted.enqueue(REDIS_QUEUE.ADSB.value)
        if not ret[0]:
            return ErrorInfo(109, f"problem during enqueue", ret[1])

        if not do_services:
            logger.debug("..done.")
            return ErrorInfo(0, "completed successfully", None)

        logger.debug("..servicing..")
        st = emit.getRelativeEmissionTime(sync)
        bt = emit.getRelativeEmissionTime(svc_sync)  # 0 for departure...
        td = bt - st
        blocktime = schedtime + timedelta(seconds=td)

        operator = Company(orgId="Airport Operator", classId="Airport Operator", typeId="Airport Operator", name="MARTAR")

        flight_service = ServiceFlight(flight, operator)
        flight_service.setManagedAirport(self.airport)
        ret = flight_service.service()
        if not ret[0]:
            return ErrorInfo(150, f"problem during flight service", ret[1])

        logger.debug("..moving service vehicle..")
        ret = flight_service.move()
        if not ret[0]:
            return ErrorInfo(151, f"problem during flight service movement creation", ret[1])

        logger.debug("..emission positions service vehicle..")
        ret = flight_service.emit()
        if not ret[0]:
            return ErrorInfo(152, f"problem during flight service emission", ret[1])

        logger.debug("..scheduling service vehicle..")
        ret = flight_service.schedule(blocktime)
        if not ret[0]:
            return ErrorInfo(153, f"problem during flight service scheduling", ret[1])

        logger.debug("..saving service vehicle..")
        if SAVE_TO_FILE:
            ret = flight_service.save()
            if not ret[0]:
                return ErrorInfo(154, f"problem during flight service scheduling", ret[1])
        ret = flight_service.saveDB()
        if not ret[0]:
            return ErrorInfo(155, f"problem during flight service save in Redis", ret[1])

        logger.debug("..done, service included.")
        return ErrorInfo(0, "completed successfully", None)


    def do_service(self, operator, service, quantity, ramp, aircraft, vehicle_ident, vehicle_icao24, vehicle_model, vehicle_startpos, vehicle_endpos, scheduled):
        logger.debug("loading aircraft..")
        actype = AircraftPerformance.find(aircraft)
        if actype is None:
            return ErrorInfo(510, f"EmitApp:do_service: aircraft performance {aircraft} not found", None)
        actype.load()
        logger.debug(f"..done {actype.available}")

        operator = Company(orgId="Airport Operator", classId="Airport Operator", typeId="Airport Operator", name="MARTAR")

        logger.debug("creating single service..")
        this_service = Service.getService(service)(operator=operator, quantity=quantity)
        rampval = self.airport.getRamp(ramp)
        if rampval is None:
            return ErrorInfo(511, f"EmitApp:do_service: ramp {ramp} not found", None)
        this_service.setRamp(rampval)
        this_service.setAircraftType(actype)
        this_vehicle = self.airport.manager.selectServiceVehicle(operator=operator, service=this_service, model=vehicle_model, registration=vehicle_ident, use=True)
        if this_vehicle is None:
            return ErrorInfo(512, f"EmitApp:do_service: vehicle not found", None)
        this_vehicle.setICAO24(vehicle_icao24)
        startpos = self.airport.selectServicePOI(vehicle_startpos, service)
        if startpos is None:
            return ErrorInfo(513, f"EmitApp:do_service: start position {vehicle_startpos} for {service} not found", None)
        this_vehicle.setPosition(startpos)
        nextpos = self.airport.selectServicePOI(vehicle_endpos, service)
        if nextpos is None:
            return ErrorInfo(513, f"EmitApp:do_service: start position {vehicle_endpos} for {service} not found", None)
        this_service.setNextPosition(nextpos)

        logger.debug(".. moving ..")
        move = ServiceMove(this_service, self.airport)
        ret = move.move()
        if not ret[0]:
            return ErrorInfo(514, f"problem during service move", ret[1])
        if SAVE_TO_FILE:
            ret = move.save()
            if not ret[0]:
                return ErrorInfo(514, f"problem during service move save", ret[1])
        logger.debug(".. emission positions ..")
        emit = Emit(move)
        ret = emit.emit()
        if not ret[0]:
            return ErrorInfo(514, f"problem during service emission", ret[1])

        logger.debug(emit.getMarkList())
        service_duration = this_service.serviceDuration()

        logger.debug(f".. service duration {service_duration} ..")
        emit.addToPause(SERVICE_PHASE.SERVICE_START.value, service_duration)
        # will trigger new call to emit.emit() to adjust

        logger.debug(".. scheduling broadcast ..")
        # default is to serve at scheduled time
        logger.debug(f".. {SERVICE_PHASE.SERVICE_START.value} at {scheduled} ..")
        ret = emit.schedule(SERVICE_PHASE.SERVICE_START.value, datetime.fromisoformat(scheduled))
        if not ret[0]:
            return ErrorInfo(514, f"problem during service scheduling", ret[1])
        if SAVE_TO_FILE:
            ret = emit.save()
            if not ret[0]:
                return ErrorInfo(514, f"problem during service emission save", ret[1])
        ret = emit.saveDB()
        if not ret[0]:
            return ErrorInfo(514, f"problem during service emission save to Redis", ret[1])

        logger.debug(".. broadcasting position ..")
        formatted = FormatToRedis(emit, LiveTraffic)
        ret = formatted.format()
        if not ret[0]:
            return ErrorInfo(514, f"problem during service formatting", ret[1])
        ret = formatted.save(overwrite=True)
        if not ret[0] and ret[1] != "FormatToRedis::save key already exist":
            return ErrorInfo(514, f"problem during service save", ret[1])
        ret = formatted.enqueue(REDIS_QUEUE.ADSB.value)
        if not ret[0]:
            return ErrorInfo(514, f"problem during service save to Redis", ret[1])

        logger.debug("..done")

        return ErrorInfo(0, "completed successfully", len(emit._emit))


    def do_mission(self, operator, checkpoints, vehicle_ident, vehicle_icao24, vehicle_model, vehicle_startpos, vehicle_endpos, scheduled):
        return ErrorInfo(1, "unimplemented", None)


    def do_schedule(self, ident, sync, scheduled):
        ident2 = ident.replace("-enqueued", "")
        emit = ReEmit(ident2)
        ret = emit.schedule(sync, datetime.fromisoformat(scheduled))
        if not ret[0]:
            return ErrorInfo(160, f"problem during rescheduling", ret[1])

        logger.debug("..broadcasting positions..")
        formatted = FormatToRedis(emit, LiveTraffic)
        ret = formatted.format()
        if not ret[0]:
            return ErrorInfo(160, f"problem during rescheduled formatting", ret[1])
        ret = formatted.save(overwrite=True)
        if not ret[0]:
            return ErrorInfo(160, f"problem during rescheduled save", ret[1])
        ret = formatted.enqueue(REDIS_QUEUE.ADSB.value)
        if not ret[0]:
            return ErrorInfo(160, f"problem during rescheduled enqueing", ret[1])
        logger.debug("..done.")

        return ErrorInfo(0, "rescheduled successfully", None)


    def do_delete(self, ident):
        ret = FormatToRedis.delete(ident)
        if not ret[0]:
            return ErrorInfo(190, f"problem during deletion of {ident} ", ret)
        return ErrorInfo(0, "deleted successfully", None)

