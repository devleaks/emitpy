"""
Creates all services required for a flight, depends on movement, ramp, and actype.
"""
import io
import logging
from datetime import datetime, timedelta

from tabulate import tabulate

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
        self.app = None
        self.flight = flight
        self.operator = operator
        self.ramp = flight.ramp  # should check that aircraft was not towed to another ramp for departure.
        self.actype = flight.aircraft.actype
        self.services = []
        self.airport = None


    @staticmethod
    def getFlightServicesKey(flight_id: str):
        return key_path(REDIS_DATABASE.FLIGHTS.value, flight_id, REDIS_DATABASE.SERVICES.value)


    def setManagedAirport(self, managedAirport):
        self.app = managedAirport
        self.airport = managedAirport.airport

    # #######################
    # Saving to file or Redis
    #
    def save(self, redis):
        for service in self.services:
            logger.debug(f"saving to redis {service['type']}..")
            emit = service["emit"]
            ret = emit.save(redis)
            if not ret[0]:
                logger.warning(f"{service['type']} returned {ret[1]}")
            else:
                logger.debug(f"..done")
        self.saveServicesForFlight(redis)
        return (True, "FlightServices::save: completed")


    def saveFile(self):
        for service in self.services:
            logger.debug(f"saving to file {service['type']}..")
            emit = service["emit"]
            ret = emit.saveFile()
            if not ret[0]:
                logger.warning(f"{service['type']} returned {ret[1]}")
            else:
                logger.debug(f"..done")
        return (True, "FlightServices::saveFile: completed")


    def saveServicesForFlight(self, redis):
        if redis is None:
            return (True, "FlightServices::saveServicesForFlight: no Redis")
        if self.flight is None:
            return (False, "FlightServices::saveServicesForFlight: no flight")

        base = FlightServices.getFlightServicesKey(self.flight.getId())
        for service in self.services:
            s = service["service"]
            redis.sadd(base, s.getId())
        return (True, "FlightServices::saveServicesForFlight: saved")


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
        #   type: baggage
        #   model: train
        #   start: 10
        #   duration: 20
        #   alert: 5
        #   warn: 0
        #
        # event:
        #   type: event
        #   event: First passenger exits aircraft
        #   start: 10
        #   warn: 0
        #   alert: 5
        #
        for svc in svcs:
            sname = svc.get(TAR_SERVICE.TYPE.value)
            scheduled = svc.get(TAR_SERVICE.START.value)
            duration = svc.get(TAR_SERVICE.DURATION.value, 0)
            warn_time = svc.get(TAR_SERVICE.WARN.value)
            alert_time = svc.get(TAR_SERVICE.ALERT.value)
            label = svc.get(TAR_SERVICE.LABEL.value)

            logger.debug(f"creating service {sname}..")

            service_scheduled_dt = self.flight.scheduled_dt + timedelta(minutes=scheduled)
            service_scheduled_end_dt = self.flight.scheduled_dt + timedelta(minutes=(scheduled+duration))
            this_service = Service.getService(sname)(scheduled=service_scheduled_dt,
                                                     ramp=self.flight.ramp,
                                                     operator=self.operator)

            if self.flight.load_factor != 1.0:  # Wow
                duration = duration * self.flight.load_factor

            this_service.setPTS(relstartime=scheduled, duration=duration, warn=warn_time, alert=alert_time)
            this_service.setFlight(self.flight)
            this_service.setAircraftType(self.flight.aircraft.actype)
            this_service.setRamp(self.ramp)
            if label is not None:
                this_service.setLabel(label)
            if sname == EVENT_ONLY_MESSAGE:  # TA service with no vehicle, we just emit messages on the wire
                label = svc.get(TAR_SERVICE.LABEL.value)  # Important to set it here, since not provided at creation
                if label is None:
                    this_service.label = this_service.getId()
                    logger.warning(f"event service {svc} has no label, created event only service with label «{this_service.label}»..")
                else:
                    this_service.label = label
                    logger.debug(f"created event only service with label «{this_service.label}»..")
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
                    logger.warning(f"positions: {equipment_startpos} -> {equipment_endpos}")
                # logger.debug(".. moving ..")
                # move = ServiceMove(this_service, self.airport)
                # move.move()
                # move.save()

            logger.debug(f".. adding ..")
            s2 = svc.copy()
            s2["service"] = this_service
            self.services.append(s2)
            logger.debug(".. done")

        return (True, "FlightServices::service: completed")


    # #######################
    # Moving
    #
    def move(self):
        for service in self.services:
            logger.debug(f"moving {service['type']}..")
            move = ServiceMove(service["service"], self.airport)
            ret = move.move()
            if not ret[0]:
                logger.warning(f"moving {service['type']} returns {ret}")
                return ret
            service["move"] = move
            logger.debug(f"..done")
        return (True, "FlightServices::move: completed")


    # #######################
    # Emitting
    #
    def emit(self, emit_rate: int):
        for service in self.services:
            logger.debug(f"emitting {service['type']}..")
            emit = Emit(service["move"])
            ret = emit.emit(emit_rate)
            if not ret[0]:
                return ret
            service["emit"] = emit
            logger.debug(f"..done")
        return (True, "FlightServices::emit: completed")


    # #######################
    # Scheduling
    #
    def schedule(self, scheduled: datetime, do_print: bool = False):
        # The scheduled date time recevied should be
        # ONBLOCK time for arrival
        # OFFBLOCK time for departure
        for service in self.services:
            emit = service["emit"]
            if emit.has_no_move_ok():
                logger.debug(f"service {service[TAR_SERVICE.TYPE.value]} does not need scheduling of positions")
                continue
            logger.debug(f"scheduling {service[TAR_SERVICE.TYPE.value]}..")
            stime = scheduled + timedelta(minutes=service[TAR_SERVICE.START.value])  # nb: service["scheduled"] can be negative
            ret = emit.schedule(SERVICE_PHASE.SERVICE_START.value, stime, do_print)
            if not ret[0]:
                return ret
            logger.debug(f"there are {len(emit.scheduled_emit)} scheduled emit points")
            logger.debug(f"..done")
        return (True, "FlightServices::schedule: completed")


    def scheduleMessages(self, scheduled: datetime, do_print: bool = False):
        for service in self.services:
            emit = service["emit"]
            logger.debug(f"scheduling {service[TAR_SERVICE.TYPE.value]}..")
            stime = scheduled + timedelta(minutes=service[TAR_SERVICE.START.value])  # nb: service["scheduled"] can be negative
            ret = emit.scheduleMessages(SERVICE_PHASE.SERVICE_START.value, stime, do_print)
            if not ret[0]:
                return ret
            logger.debug(f"there are {len(emit.getMessages())} scheduled messages")
            logger.debug(f"..done")

        # For debugging purpose only:
        if do_print:
            dummy = self.getTimedMessageList(scheduled)

        return (True, "FlightServices::scheduleMessages: completed")


    # #######################
    # Summary
    # (Mainly for debugging purpose.)
    #
    #   flight information | on/off block time
    #   Refueling | start_rel | duration | warn | alert | start time | warn time | alert time | end time | warn time | alert time
    def getTimedMessageList(self, scheduled: datetime):
        output = io.StringIO()

        print("\n", file=output)
        print(self.flight, file=output)
        print(f"block time: {scheduled.isoformat()}", file=output)

        print(f"PRECISION TIME SCHEDULE", file=output)
        PTS_HEADERS = ["event", "start", "duration", "warn", "alert", "start time", "warn time", "alert time", "end time", "end warn time", "end alert time"]
        table = []
        for service in self.services:
            s = service["service"]
            line = []
            sty = type(s).__name__.replace("Service", "").lower()
            if sty == EVENT_ONLY_MESSAGE:
                sty = s.label
            line.append(sty)
            line.append(s.pts_reltime)
            line.append(s.pts_duration)
            line.append(s.pts_warn)
            line.append(s.pts_alert)
            line.append(scheduled + timedelta(minutes=s.pts_reltime))
            if s.pts_warn is not None:
                line.append(scheduled + timedelta(minutes=s.pts_reltime + s.pts_warn))
            else:
                line.append(None)
            if s.pts_alert is not None:
                line.append(scheduled + timedelta(minutes=s.pts_reltime + s.pts_alert))
            else:
                line.append(None)
            line.append(scheduled + timedelta(minutes=s.pts_reltime + s.pts_duration))
            if s.pts_warn is not None:
                line.append(scheduled + timedelta(minutes=s.pts_reltime + s.pts_duration + s.pts_warn))
            else:
                line.append(None)
            if s.pts_alert is not None:
                line.append(scheduled + timedelta(minutes=s.pts_reltime + s.pts_duration + s.pts_alert))
            else:
                line.append(None)
            table.append(line)
        print(tabulate(table, headers=PTS_HEADERS), file=output)

        print(f"MESSAGES", file=output)
        MESSAGE_HEADERS = ["object", "type", "emission time", "subject"]
        table = []
        # for m in self.flight.getMessages():
        #     line = []
        #     line.append("flight")
        #     line.append(type(m).__name__)
        #     line.append(m.getAbsoluteEmissionTime())
        #     line.append(m.subject)
        #     table.append(line)

        for m in self.flight.get_movement().getMessages():  # move.getMessages() includes flight.getMessages()
            line = []
            line.append("move")
            line.append(type(m).__name__)
            line.append(m.getAbsoluteEmissionTime())
            line.append(m.subject)
            table.append(line)

        for service in self.services:
            s = service["service"]
            sty = type(s).__name__.replace("Service", "").lower()
            if sty == EVENT_ONLY_MESSAGE:
                sty = s.label
            s = service["move"]
            msgs = s.getMessages()
            for m in s.getMessages():
                line = []
                line.append(sty)
                line.append(type(m).__name__)
                line.append(m.getAbsoluteEmissionTime())
                line.append(m.subject)
                table.append(line)

        table = sorted(table, key=lambda x: x[2])  # absolute emission time
        print(tabulate(table, headers=MESSAGE_HEADERS), file=output)
        contents = output.getvalue()
        output.close()

        logger.debug(f"{contents}")
        return contents


    # #######################
    # Formatting
    #
    def format(self, saveToFile: bool = False):
        for service in self.services:
            emit = service["emit"]
            if emit.has_no_move_ok():
                logger.debug(f"service {service[TAR_SERVICE.TYPE.value]} does not need formatting of positions")
                continue
            logger.debug(f"formatting '{service['type']}' ({len(service['emit'].moves)}, {len(service['emit']._emit_points)}, {len(service['emit'].scheduled_emit)})..")
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
            logger.debug(f"formatting '{service['type']}' ({len(service['emit'].moves)}, {len(service['emit']._emit_points)}, {len(service['emit'].scheduled_emit)})..")
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
                logger.debug(f"service {service[TAR_SERVICE.TYPE.value]} does not need enqueueing positions")
                continue
            logger.debug(f"enqueuing '{service[TAR_SERVICE.TYPE.value]}'..")
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
            logger.debug(f"enqueuing '{service[TAR_SERVICE.TYPE.value]}'..")
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

