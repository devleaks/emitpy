import logging
import json
import random

from datetime import datetime, timedelta

from emitpy.managedairport import ManagedAirport
from emitpy.business import Airline, Company
from emitpy.aircraft import AircraftType, AircraftPerformance, Aircraft
from emitpy.flight import Arrival, Departure, ArrivalMove, DepartureMove
from emitpy.service import Service, ServiceMove, ServiceFlight, Mission, MissionMove
from emitpy.emit import Emit, ReEmit, EnqueueToRedis, Queue
from emitpy.business import AirportManager
from emitpy.constants import SERVICE, SERVICE_PHASE, MISSION_PHASE, FLIGHT_PHASE, REDIS_QUEUE, REDIS_TYPE
from emitpy.parameters import DEFAULT_QUEUES
from emitpy.airport import Airport, AirportBase
from emitpy.airspace import Metar
from emitpy.utils import NAUTICAL_MILE


logger = logging.getLogger("EmitApp")


class StatusInfo:

    def __init__(self, status: int, message: str, data):
        self.status = status
        self.message = message
        self.data = data

    def __str__(self):
        return json.dumps({
            "status": self.status,
            "message": self.message,
            "data": self.data
        })


SAVE_TO_FILE = False


class EmitApp(ManagedAirport):

    def __init__(self, airport):
        ManagedAirport.__init__(self, airport)
        # Default queue(s)
        for k, v in DEFAULT_QUEUES.items():
            default_queue = Queue(name=k, formatter_name=v)
            default_queue.save()
        self.queues = Queue.loadAllQueuesFromDB()
        self.init()


    def do_flight(self, queue, emit_rate, airline, flightnumber, scheduled, apt, movetype, acarr, ramp, icao24, acreg, runway, do_services: bool = False, actual_datetime: str = None):
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
        remote_metar = Metar(icao=remote_apt.icao, use_redis=True)
        remote_apt.setMETAR(metar=remote_metar)  # calls prepareRunways()
        logger.debug("..done")

        logger.debug("loading aircraft..")
        actype, acsubtype = acarr
        ac = AircraftPerformance.findAircraftByType(actype, acsubtype)
        if ac is None:
            return StatusInfo(100, f"aircraft performance not found for {actype} or {acsubtype}", None)
        acperf = AircraftPerformance.find(icao=ac)
        if acperf is None:
            return StatusInfo(101, f"aircraft performance not found for {ac}", None)
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
            return StatusInfo(102, f"ramp {ramp} not found", None)

        flight.setRamp(rampval)
        gate = "C99"
        ramp_name = rampval.getProp("name")
        if ramp_name[0] in "A,B,C,D,E".split(",") and len(ramp) < 5:  # does now work for "Cargo Ramp F5" ;-)
            gate = ramp_name
        flight.setGate(gate)

        aircraft.setCallsign(airline.icao+flightnumber)

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
            return StatusInfo(103, f"problem during move", ret[1])
        # move.save()

        logger.debug("..emission positions..")
        emit = Emit(move)
        ret = emit.emit(emit_rate)
        if not ret[0]:
            return StatusInfo(104, f"problem during emit", ret[1])
        # emit.save()

        logger.debug("..scheduling..")
        # Schedule actual time if supplied
        emit_time_str = actual_datetime if actual_datetime is not None else scheduled
        emit_time = datetime.fromisoformat(emit_time_str)

        logger.debug(emit.getMarkList())
        ret = emit.schedule(sync, emit_time)
        if not ret[0]:
            return StatusInfo(105, f"problem during schedule", ret[1])

        logger.debug("..saving..")
        if SAVE_TO_FILE:
            ret = emit.save()
            if not ret[0]:
                return StatusInfo(105, f"problem during schedule", ret[1])
        ret = emit.saveDB()
        if not ret[0]:
            return StatusInfo(110, f"problem during schedule", ret[1])
        logger.info("SAVED " + ("*" * 84))
        logger.debug("..broadcasting positions..")
        formatted = EnqueueToRedis(emit, self.queues[queue])
        ret = formatted.format()
        if not ret[0]:
            return StatusInfo(107, f"problem during formatting", ret[1])
        ret = formatted.save()
        if not ret[0] and ret[1] != "FormatToRedis::save key already exist":
            return StatusInfo(108, f"problem during formatted output save", ret[1])
        ret = formatted.enqueue()
        if not ret[0]:
            return StatusInfo(109, f"problem during enqueue", ret[1])

        if not do_services:
            logger.debug("..done.")
            return StatusInfo(0, "completed successfully", None)

        logger.debug("..servicing..")
        st = emit.getRelativeEmissionTime(sync)
        bt = emit.getRelativeEmissionTime(svc_sync)  # 0 for departure...
        td = bt - st
        blocktime = emit_time + timedelta(seconds=td)

        operator = Company(orgId="Airport Operator", classId="Airport Operator", typeId="Airport Operator", name="MARTAR")

        flight_service = ServiceFlight(flight, operator)
        flight_service.setManagedAirport(self.airport)
        ret = flight_service.service()
        if not ret[0]:
            return StatusInfo(150, f"problem during flight service", ret[1])

        logger.debug("..moving service vehicle..")
        ret = flight_service.move()
        if not ret[0]:
            return StatusInfo(151, f"problem during flight service movement creation", ret[1])

        logger.debug("..emission positions service vehicle..")
        ret = flight_service.emit(emit_rate)
        if not ret[0]:
            return StatusInfo(152, f"problem during flight service emission", ret[1])

        logger.debug("..scheduling service vehicle..")
        ret = flight_service.schedule(blocktime)
        if not ret[0]:
            return StatusInfo(153, f"problem during flight service scheduling", ret[1])

        logger.debug("..saving service vehicle..")
        if SAVE_TO_FILE:
            ret = flight_service.save()
            if not ret[0]:
                return StatusInfo(154, f"problem during flight service scheduling", ret[1])
        ret = flight_service.saveDB()
        if not ret[0]:
            return StatusInfo(155, f"problem during flight service save in Redis", ret[1])

        logger.debug("..done, service included.")
        return StatusInfo(0, "completed successfully", None)


    def do_service(self, queue, emit_rate, operator, service, quantity, ramp, aircraft, vehicle_ident, vehicle_icao24, vehicle_model, vehicle_startpos, vehicle_endpos, scheduled):
        logger.debug("loading aircraft..")
        actype = AircraftPerformance.find(aircraft)
        if actype is None:
            return StatusInfo(510, f"EmitApp:do_service: aircraft performance {aircraft} not found", None)
        actype.load()
        logger.debug(f"..done {actype.available}")

        operator = Company(orgId="Airport Operator", classId="Airport Operator", typeId="Airport Operator", name="MARTAR")

        logger.debug("creating service..")
        this_service = Service.getService(service)(operator=operator, quantity=quantity)
        rampval = self.airport.getRamp(ramp)
        if rampval is None:
            return StatusInfo(511, f"EmitApp:do_service: ramp {ramp} not found", None)
        this_service.setRamp(rampval)
        this_service.setAircraftType(actype)
        this_vehicle = self.airport.manager.selectServiceVehicle(operator=operator, service=this_service, model=vehicle_model, registration=vehicle_ident, use=True)
        if this_vehicle is None:
            return StatusInfo(512, f"EmitApp:do_service: vehicle not found", None)
        this_vehicle.setICAO24(vehicle_icao24)
        startpos = self.airport.selectServicePOI(vehicle_startpos, service)
        if startpos is None:
            return StatusInfo(513, f"EmitApp:do_service: start position {vehicle_startpos} for {service} not found", None)
        this_vehicle.setPosition(startpos)
        nextpos = self.airport.selectServicePOI(vehicle_endpos, service)
        if nextpos is None:
            return StatusInfo(513, f"EmitApp:do_service: start position {vehicle_endpos} for {service} not found", None)
        this_vehicle.setNextPosition(nextpos)

        logger.debug(".. moving ..")
        move = ServiceMove(this_service, self.airport)
        ret = move.move()
        if not ret[0]:
            return StatusInfo(514, f"problem during service move", ret[1])
        if SAVE_TO_FILE:
            ret = move.save()
            if not ret[0]:
                return StatusInfo(514, f"problem during service move save", ret[1])
        logger.debug(".. emission positions ..")
        emit = Emit(move)
        ret = emit.emit(emit_rate)
        if not ret[0]:
            return StatusInfo(514, f"problem during service emission", ret[1])

        logger.debug(emit.getMarkList())
        service_duration = this_service.serviceDuration()

        logger.debug(f".. service duration {service_duration} ..")
        emit.addToPause(SERVICE_PHASE.SERVICE_START.value, service_duration)
        # will trigger new call to emit.emit(emit_rate) to adjust

        logger.debug(".. scheduling broadcast ..")
        # default is to serve at scheduled time
        logger.debug(f".. {SERVICE_PHASE.SERVICE_START.value} at {scheduled} ..")
        ret = emit.schedule(SERVICE_PHASE.SERVICE_START.value, datetime.fromisoformat(scheduled))
        if not ret[0]:
            return StatusInfo(514, f"problem during service scheduling", ret[1])
        if SAVE_TO_FILE:
            ret = emit.save()
            if not ret[0]:
                return StatusInfo(514, f"problem during service emission save", ret[1])
        ret = emit.saveDB()
        if not ret[0]:
            return StatusInfo(514, f"problem during service emission save to Redis", ret[1])

        logger.debug(".. broadcasting position ..")
        formatted = EnqueueToRedis(emit, self.queues[queue])
        ret = formatted.format()
        if not ret[0]:
            return StatusInfo(514, f"problem during service formatting", ret[1])
        ret = formatted.save(overwrite=True)
        if not ret[0] and ret[1] != "EnqueueToRedis::save key already exist":
            return StatusInfo(514, f"problem during service save", ret[1])
        ret = formatted.enqueue()
        if not ret[0]:
            return StatusInfo(514, f"problem during service save to Redis", ret[1])

        logger.debug("..done")

        return StatusInfo(0, "completed successfully", len(emit._emit))


    def do_mission(self, emit_rate, queue, operator, checkpoints, mission, vehicle_ident, vehicle_icao24, vehicle_model, vehicle_startpos, vehicle_endpos, scheduled):
        if len(checkpoints) == 0:
            checkpoints = [c[0] for c in random.choices(self.airport.getPOICombo(), k=3)]

        logger.debug("creating mission..")
        operator = Company(orgId="Airport Security", classId="Airport Operator", typeId="Airport Operator", name=operator)
        mission = Mission(operator=operator, checkpoints=checkpoints, name=mission)

        mission_vehicle = self.airport.manager.selectServiceVehicle(operator=operator, service=mission, model=vehicle_model, registration=vehicle_ident, use=True)
        mission_vehicle.setICAO24(vehicle_icao24)

        start_pos = self.airport.getPOI(vehicle_startpos)
        if start_pos is None:
            return StatusInfo(614, f"connot find start position {vehicle_startpos}", None)
        mission_vehicle.setPosition(start_pos)
        end_pos = self.airport.getPOI(vehicle_endpos)
        if end_pos is None:
            return StatusInfo(614, f"connot find end position {vehicle_endpos}", None)
        mission_vehicle.setNextPosition(end_pos)

        # logger.debug("..running..")
        # mission.run()  # do nothing...

        logger.debug(".. moving ..")
        move = MissionMove(mission, self.airport)
        ret = move.move()
        if not ret[0]:
            return StatusInfo(614, f"problem during mission move", ret[1])
        if SAVE_TO_FILE:
            ret = move.save()
            if not ret[0]:
                return StatusInfo(614, f"problem during mission move save", ret[1])

        logger.debug(".. emission positions ..")
        emit = Emit(move)
        ret = emit.emit(emit_rate)
        if not ret[0]:
            return StatusInfo(614, f"problem during mission emission", ret[1])

        logger.debug(".. scheduling broadcast ..")
        logger.debug(emit.getMarkList())
        ret = emit.schedule(MISSION_PHASE.START.value, datetime.fromisoformat(scheduled))
        if not ret[0]:
            return StatusInfo(514, f"problem during mission scheduling", ret[1])
        if SAVE_TO_FILE:
            ret = emit.save()
            if not ret[0]:
                return StatusInfo(514, f"problem during mission emission save", ret[1])
        ret = emit.saveDB()
        if not ret[0]:
            return StatusInfo(514, f"problem during service mission save to Redis", ret[1])

        logger.debug(".. broadcasting position ..")
        formatted = EnqueueToRedis(emit, self.queues[queue])
        ret = formatted.format()
        if not ret[0]:
            return StatusInfo(614, f"problem during service formatting", ret[1])
        ret = formatted.save(overwrite=True)
        if not ret[0] and ret[1] != "EnqueueToRedis::save key already exist":
            return StatusInfo(615, f"problem during service save", ret[1])
        ret = formatted.enqueue()
        if not ret[0]:
            return StatusInfo(616, f"problem during service save to Redis", ret[1])

        logger.debug("..done")
        return StatusInfo(0, "do_mission completed successfully", None)


    def do_schedule(self, queue, ident, sync, scheduled):
        emit = ReEmit(ident)
        ret = emit.schedule(sync, datetime.fromisoformat(scheduled))
        if not ret[0]:
            return StatusInfo(160, f"problem during rescheduling", ret[1])

        logger.debug("..broadcasting positions..")
        formatted = EnqueueToRedis(emit, self.queues[queue])
        ret = formatted.format()
        if not ret[0]:
            return StatusInfo(160, f"problem during rescheduled formatting", ret[1])
        ret = formatted.save(overwrite=True)
        if not ret[0]:
            return StatusInfo(160, f"problem during rescheduled save", ret[1])
        ret = formatted.enqueue()
        if not ret[0]:
            return StatusInfo(160, f"problem during rescheduled enqueing", ret[1])
        logger.debug("..done.")

        return StatusInfo(0, "rescheduled successfully", None)


    def do_delete(self, queue, ident):
        ret = EnqueueToRedis.delete(ident, queue=queue)
        if not ret[0]:
            return StatusInfo(190, f"problem during deletion of {ident} ", ret)
        return StatusInfo(0, "deleted successfully", None)


    def do_create_queue(self, name, formatting, starttime, speed):
        """
        Creates or "register" a Queue for (direct) use
        """
        q = Queue(name=name, formatter_name=formatting, starttime=starttime, speed=speed)

        ret = q.save()
        if not ret[0]:
            return StatusInfo(1, f"problem during creation of queue {name} ", ret)
        self.queues[name] = q
        return StatusInfo(0, "queue created successfully", None)


    def do_reset_queue(self, name, starttime, speed):
        """
        Reset a queue'start time
        """
        q = self.queues[name]
        ret = q.reset(speed=speed, starttime=starttime)
        if not ret[0]:
            return StatusInfo(1, f"problem during restart of queue {name} ", ret)
        return StatusInfo(0, "queue started successfully", None)


    def do_delete_queue(self, name):
        """
        Dlete a Queue
        """
        ret = Queue.delete(name)
        if not ret[0]:
            return StatusInfo(1, f"problem during deletion of queue {name} ", ret)
        del self.queues[name]
        return StatusInfo(0, "queue delete successfully", None)
