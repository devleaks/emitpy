"""
Creates all services required for a flight, depends on movement, ramp, and actype.
"""
import logging
from datetime import datetime, timedelta

from .service import Service
from .servicemovement import ServiceMove

import emitpy.service

from emitpy.flight import Flight
from emitpy.emit import Emit, ReEmit
from emitpy.broadcast import Format, FormatMessage, EnqueueToRedis, EnqueueMessagesToRedis
from emitpy.constants import TAR_SERVICE, SERVICE_PHASE, ARRIVAL, DEPARTURE, REDIS_TYPE, REDIS_DATABASE, ID_SEP, EVENT_ONLY_MESSAGE, key_path

logger = logging.getLogger("FlightServices")

class FlightServices:

    def __init__(self, flight: Flight, operator: "Company"):
        self.flight = flight
        self.operator = operator
        self.ramp = flight.ramp  # should check that aircraft was not towed to another ramp for departure.
        self.actype = flight.aircraft.actype
        self.services = []
        self.airport = None


    @staticmethod
    def allServicesForFlight(redis, flight_id: str, redis_type=REDIS_TYPE.EMIT_META.value):
        items = []
        emit = ReEmit(flight_id, redis)
        emit_meta = emit.getMeta()

        is_arrival = emit.getMeta("$.move.is_arrival")
        if is_arrival is None:
            logger.warning(f":allServicesForFlight: cannot get flight movement")
            return ()

        before = None
        if is_arrival:
            before = 60
            after = 180
        else:
            before = 180
            after = 60

        scheduled = emit.getMeta("$.move.scheduled")
        if scheduled is None:
            logger.warning(f":do_flight_services: cannot get flight scheduled time {emit.getMeta()}")
            return ()
        scheduled = datetime.fromisoformat(scheduled)

        et_min = scheduled - timedelta(minutes=before)
        et_max = scheduled + timedelta(minutes=after)
        logger.debug(f":allServicesForFlight: {ARRIVAL if is_arrival else DEPARTURE} at {scheduled}")
        logger.debug(f":allServicesForFlight: trying services between {et_min} and {et_max}")

        # 2 search for all services at that ramp, "around" supplied ETA/ETD.
        ramp = emit.getMeta("$.move.ramp.name")
        keys = redis.keys(key_path(REDIS_DATABASE.SERVICES.value, "*", ramp, "*", redis_type))
        for k in keys:
            k = k.decode("UTF-8")
            karr = k.split(ID_SEP)
            dt = datetime.fromisoformat(karr[3].replace(".", ":"))
            # logger.debug(f":allServicesForFlight: {k}: testing {dt}..")
            if dt > et_min and dt < et_max:
                items.append(k)
                logger.debug(f":allServicesForFlight: added {k}..")
        logger.debug(f":allServicesForFlight: ..done")
        return set(items)


    def setManagedAirport(self, managedAirport):
        self.app = managedAirport
        self.airport = managedAirport.airport


    # #######################
    # Saving to file or Redis
    #
    def save(self, redis):
        for service in self.services:
            logger.debug(f":save: saving to redis {service['type']}..")
            emit = service["emit"]
            ret = emit.save(redis)
            if not ret[0]:
                logger.warning(f":save: {service['type']} returned {ret[1]}")
            else:
                logger.debug(f":save: ..done")
        return (True, "FlightServices::save: completed")


    def saveFile(self):
        for service in self.services:
            logger.debug(f":saveFile: saving to file {service['type']}..")
            emit = service["emit"]
            ret = emit.saveFile()
            if not ret[0]:
                logger.warning(f":saveFile: {service['type']} returned {ret[1]}")
            else:
                logger.debug(f":saveFile: ..done")
        return (True, "FlightServices::saveFile: completed")


    # #######################
    # Servicing
    #
    def service(self):
        # From dict, make append appropriate service to list
        gseprofile = self.flight.aircraft.actype.getGSEProfile(redis=self.app.use_redis())
        if gseprofile is None:
            logger.warning(f"service: no GSE ramp profile for {self.flight.aircraft.actype.typeId}")

        tarprofile = self.flight.getTurnaroundProfile(redis=self.app.use_redis())
        if tarprofile is None:
            return (False, f"FlightServices::service: no turnaround profile for {self.flight.aircraft.actype.typeId}")

        if "services" not in tarprofile:
            return (False, f"FlightServices::service: no service in turnaround profile for {self.flight.aircraft.actype}")

        svcs = tarprofile["services"]

        am = self.airport.manager

        # services:
        # - alert: 5
        #   duration: 20
        #   model: train
        #   service: baggage
        #   start: 10
        #   warn: 0

        for svc in svcs:
            sname = svc.get(TAR_SERVICE.TYPE.value)
            scheduled = svc.get(TAR_SERVICE.START.value)
            duration = svc.get(TAR_SERVICE.DURATION.value, 0)

            logger.debug(f":service: creating service {sname}..")

            service_scheduled_dt = self.flight.scheduled_dt + timedelta(minutes=scheduled)
            service_scheduled_end_dt = self.flight.scheduled_dt + timedelta(minutes=(scheduled+duration))
            this_service = Service.getService(sname)(scheduled=service_scheduled_dt,
                                                     ramp=self.flight.ramp,
                                                     operator=self.operator)

            if self.flight.load_factor != 1.0:  # Wow
                duration = duration * self.flight.load_factor

            this_service.setPTS(relstartime=scheduled, duration=duration)
            this_service.setFlight(self.flight)
            this_service.setAircraftType(self.flight.aircraft.actype)
            this_service.setRamp(self.ramp)
            if sname == EVENT_ONLY_MESSAGE:  # TA service with no vehicle, we just emit messages on the wire
                this_service.event = svc.get(TAR_SERVICE.EVENT.value)  # Important to set it here, since not provided at creation
                # this_service.setVehicle(None)
            else:
                equipment_model = svc.get(TAR_SERVICE.MODEL.value)
                # should book vehicle a few minutes before and after...
                this_equipment = am.selectEquipment(operator=self.operator,
                                                    service=this_service,
                                                    model=equipment_model,
                                                    reqtime=service_scheduled_dt,
                                                    reqend=service_scheduled_end_dt,
                                                    use=True)  # this will attach this_equipment to this_service

                if this_equipment is None:
                    return (False, f"FlightServices::service: vehicle not found for {sname}")

                equipment_startpos = self.airport.selectRandomServiceDepot(sname)
                this_equipment.setPosition(equipment_startpos)

                equipment_endpos = self.airport.selectRandomServiceRestArea(sname)
                this_equipment.setNextPosition(equipment_endpos)

                if equipment_startpos is None or equipment_endpos is None:
                    logger.warning(f":service: positions: {equipment_startpos} -> {equipment_endpos}")
                # logger.debug(".. moving ..")
                # move = ServiceMove(this_service, self.airport)
                # move.move()
                # move.save()

            logger.debug(f":service: .. adding ..")
            s2 = svc.copy()
            s2["service"] = this_service
            self.services.append(s2)
            logger.debug(":service: .. done")

        return (True, "FlightServices::service: completed")


    # #######################
    # Moving
    #
    def move(self):
        for service in self.services:
            logger.debug(f":move: moving {service['type']}..")
            move = ServiceMove(service["service"], self.airport)
            ret = move.move()
            if not ret[0]:
                logger.warning(f"moving {service['type']} returns {ret}")
                return ret
            service["move"] = move
            logger.debug(f":move: ..done")
        return (True, "FlightServices::move: completed")


    # #######################
    # Emitting
    #
    def emit(self, emit_rate: int):
        for service in self.services:
            logger.debug(f":emit: emitting {service['type']}..")
            emit = Emit(service["move"])
            ret = emit.emit(emit_rate)
            if not ret[0]:
                return ret
            service["emit"] = emit
            logger.debug(f":emit: ..done")
        return (True, "FlightServices::emit: completed")


    # #######################
    # Scheduling
    #
    def schedule(self, scheduled: datetime):
        # The scheduled date time recevied should be
        # ONBLOCK time for arrival
        # OFFBLOCK time for departure
        for service in self.services:
            emit = service["emit"]
            if emit.has_no_move_ok():
                logger.debug(f":schedule: service {service[TAR_SERVICE.TYPE.value]} does not need scheduling of positions")
                continue
            logger.debug(f":schedule: scheduling {service[TAR_SERVICE.TYPE.value]}..")
            stime = scheduled + timedelta(minutes=service[TAR_SERVICE.START.value])  # nb: service["scheduled"] can be negative
            emit.addToPause(SERVICE_PHASE.SERVICE_START.value, service.get(TAR_SERVICE.DURATION.value, 0) * 60)  # seconds
            ret = emit.schedule(SERVICE_PHASE.SERVICE_START.value, stime)
            if not ret[0]:
                return ret
            logger.debug(f":schedule: there are {len(emit.scheduled_emit)} scheduled emit points")
            logger.debug(f":schedule: ..done")
        return (True, "FlightServices::schedule: completed")


    def scheduleMessages(self, scheduled: datetime):
        for service in self.services:
            emit = service["emit"]
            logger.debug(f":schedule: scheduling {service[TAR_SERVICE.TYPE.value]}..")
            stime = scheduled + timedelta(minutes=service[TAR_SERVICE.START.value])  # nb: service["scheduled"] can be negative
            ret = emit.scheduleMessages(SERVICE_PHASE.SERVICE_START.value, stime)
            if not ret[0]:
                return ret
            logger.debug(f":schedule: there are {len(emit.getMessages())} scheduled messages")
            logger.debug(f":schedule: ..done")
        return (True, "FlightServices::scheduleMessages: completed")


    # #######################
    # Formatting
    #
    def format(self, saveToFile: bool = False):
        for service in self.services:
            emit = service["emit"]
            if emit.has_no_move_ok():
                logger.debug(f":format: service {service[TAR_SERVICE.TYPE.value]} does not need formatting of positions")
                continue
            logger.debug(f":format: formatting '{service['type']}' ({len(service['emit'].moves)}, {len(service['emit']._emit)}, {len(service['emit'].scheduled_emit)})..")
            formatted = Format(emit)
            ret = formatted.format()
            if not ret[0]:
                return ret
            if saveToFile:
                ret = formatted.saveFile()
                logger.debug(f"..saved to file..")
                if not ret[0]:
                    return ret
            logger.debug(f"..done")
        return (True, "FlightServices::format: completed")


    def formatMessages(self, saveToFile: bool = False):
        for service in self.services:
            logger.debug(f":format: formatting '{service['type']}' ({len(service['emit'].moves)}, {len(service['emit']._emit)}, {len(service['emit'].scheduled_emit)})..")
            formatted = FormatMessage(service["emit"])
            ret = formatted.format()
            if not ret[0]:
                return ret
            if saveToFile:
                ret = formatted.saveFile()
                logger.debug(f"..saved to file..")
                if not ret[0]:
                    return ret
            logger.debug(f"..done")
        return (True, "FlightServices::formatmessages: completed")


    # #######################
    # To Redis
    #
    def enqueueToRedis(self, queue):
        for service in self.services:
            emit = service["emit"]
            if emit.has_no_move_ok():
                logger.debug(f":enqueuetoredis: service {service[TAR_SERVICE.TYPE.value]} does not need enqueueing positions")
                continue
            logger.debug(f":enqueuetoredis: enqueuing '{service[TAR_SERVICE.TYPE.value]}'..")
            formatted = EnqueueToRedis(emit, queue)
            ret = formatted.format()
            if not ret[0]:
                return ret
            # ret = formatted.save()
            # if not ret[0] and ret[1] != "EnqueueToRedis::save key already exist":
            #     return ret
            ret = formatted.enqueue()
            if not ret[0]:
                return ret
            logger.debug(f"..done")
        return (True, "FlightServices::enqueuetoredis: completed")


    def enqueueMessagesToRedis(self, queue):
        for service in self.services:
            emit = service["emit"]
            logger.debug(f":enqueuemessagestoredis: enqueuing '{service[TAR_SERVICE.TYPE.value]}'..")
            formatted = EnqueueMessagesToRedis(emit, queue)
            ret = formatted.format()
            if not ret[0]:
                return ret
            # ret = formatted.save()
            # if not ret[0] and ret[1] != "EnqueueToRedis::save key already exist":
            #     return ret
            ret = formatted.enqueue()
            if not ret[0]:
                return ret
            logger.debug(f"..done")
        return (True, "FlightServices::enqueuemessagestoredis: completed")


loggerta = logging.getLogger("Turnaround")


class Turnaround:
    """
    Calls FlightServices on a pair of flights.
    Convenience wrapper around a pair of linked, related flight and their FlightServices.
    Add ability to tow aircraft between arrival and departure. (currently unused.)
    """

    def __init__(self, arrival: Flight, departure: Flight, operator: "Company"):
        arrival.setLinkedFlight(departure)
        self.arrival = FlightServices(arrival, operator)
        self.departure = FlightServices(departure, operator)
        self.airport = None
        arrival.setLinkedFlight(linked_flight=departure)  # will do the reverse as well
        if self.is_towed():
            loggerta.warning(":init: aircraft towed between linked flights")
            # Should here create an aircraft/tow service
            # Can be scheduled later.

    def is_towed(self) -> bool:
        return self.arrival.flight.ramp != self.departure.flight.ramp

    def getTowMovement(self):
        pass

    def scheduleTowMovement(self):
        pass

    def emitTowMovement(self):
        pass

    def setManagedAirport(self, airport):
        self.airport = airport
        self.arrival.setManagedAirport(airport)
        self.departure.setManagedAirport(airport)

    def service(self):
        # If towed, should schedule towing
        self.arrival.service()
        self.departure.service()

    def move(self):
        self.arrival.move()
        self.departure.move()

    def emit(self, emit_rate: int):
        self.arrival.emit(emit_rate)
        self.departure.emit(emit_rate)

    def save(self, redis):
        self.arrival.save(redis)
        self.departure.save(redis)

