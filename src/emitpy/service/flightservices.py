"""
Creates all services required for a flight, depends on movement, ramp, and actype.
"""
import io
import logging
from datetime import datetime, timedelta

from tabulate import tabulate

from .service import Service
from .servicemovement import ServiceMovement

import emitpy.service

from emitpy.flight import Flight
from emitpy.emit import Emit, ReEmit
from emitpy.broadcast import (
    Format,
    FormatMessage,
    EnqueueToRedis,
    EnqueueMessagesToRedis,
)
from emitpy.constants import (
    TAR_SERVICE,
    SERVICE_PHASE,
    ARRIVAL,
    DEPARTURE,
    REDIS_TYPE,
    REDIS_DATABASE,
    ID_SEP,
    EVENT_ONLY_MESSAGE,
    key_path,
)

logger = logging.getLogger("FlightServices")


class FlightServices:
    def __init__(self, flight: Flight, operator: "Company"):
        self.app = None
        self.flight = flight
        self.operator = operator
        self.ramp = (
            flight.ramp
        )  # should check that aircraft was not towed to another ramp for departure.
        self.actype = flight.aircraft.actype
        self.services = []
        self.airport = None

    @staticmethod
    def getFlightServicesKey(flight_id: str):
        return key_path(
            REDIS_DATABASE.FLIGHTS.value, flight_id, REDIS_DATABASE.SERVICES.value
        )

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
        gseprofile = self.flight.aircraft.actype.getGSEProfile(
            redis=self.app.use_redis()
        )
        if gseprofile is None:
            logger.warning(
                f"service: no GSE ramp profile for {self.flight.aircraft.actype.typeId}"
            )

        tarprofile = self.flight.getTurnaroundProfile(redis=self.app.use_redis())
        if tarprofile is None:
            return (
                False,
                f"FlightServices::service: no turnaround profile for {self.flight.aircraft.actype.typeId}",
            )

        if "services" not in tarprofile:
            return (
                False,
                f"FlightServices::service: no service in turnaround profile for {self.flight.aircraft.actype}",
            )

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
            warn_time = svc.get(TAR_SERVICE.WARN.value)
            alert_time = svc.get(TAR_SERVICE.ALERT.value)
            label = svc.get(TAR_SERVICE.LABEL.value)
            duration = svc.get(TAR_SERVICE.DURATION.value)
            quantity = svc.get(TAR_SERVICE.QUANTITY.value)

            logger.debug(f"creating service {sname}..")

            # Create service
            service_scheduled_dt = self.flight.scheduled_dt + timedelta(
                minutes=scheduled
            )
            this_service = Service.getService(sname)(
                scheduled=service_scheduled_dt,
                ramp=self.flight.ramp,
                operator=self.operator,
            )

            this_service.setFlight(self.flight)
            this_service.setAircraftType(self.flight.aircraft.actype)
            this_service.setRamp(self.ramp)
            if label is None:
                label = this_service.getId()
                logger.warning(
                    f"..service {sname} has no label, added label «{label}».."
                )
            this_service.setLabel(label)

            # 2 cases: Event or regular
            if this_service.is_event():
                this_service.setVehicle(None)
                # there is no "quantity"
                if quantity is not None:
                    logger.debug(f"..event only service ignoring quantity..")
                if duration is None:
                    logger.debug(f"..event only service forced missing duration to 0..")
                    duration = 0
                if duration > 0 and self.flight.load_factor != 1.0:  # Wow
                    logger.debug(
                        f"service {sname}: reduced duration: load factor={self.flight.load_factor}"
                    )
                    duration = duration * self.flight.load_factor
                this_service.setRSTSchedule(
                    relstartime=scheduled,
                    duration=duration,
                    warn=warn_time,
                    alert=alert_time,
                )  # duration in minutes
                logger.debug(
                    f"..created event only service with label «{this_service.label}».."
                )
            else:
                equipment_model = svc.get(TAR_SERVICE.MODEL.value)
                # should book vehicle a few minutes before and after...
                # chicken/egg problem: for quantity based service, we need to know which vehicle
                # before we can compute the duration...

                service_scheduled_end_dt = None
                # Duration or quantity?
                if duration is not None and quantity is not None:
                    logger.warning(
                        f"{sname} has both duration and quantity, using quantity"
                    )
                    duration = None

                if duration is None and quantity is None:
                    duration = this_service.duration()
                    service_scheduled_end_dt = service_scheduled_dt + timedelta(
                        seconds=duration
                    )
                    this_service.setRSTSchedule(
                        relstartime=scheduled,
                        duration=duration / 60,
                        warn=warn_time,
                        alert=alert_time,
                    )
                    logger.warning(
                        f"{sname} has no duration and no quantity, using default duration {duration} min"
                    )

                if duration is None and quantity is not None:
                    this_service.setQuantity(quantity)
                    # This will be done in selectEquipment()
                    # duration = this_equipment.getDuration(quantity=quantity)
                    logger.debug(
                        f"{sname} uses quantity, duration estimated during vehicle assignment"
                    )

                if duration is not None and quantity is None:
                    this_service.setRSTSchedule(
                        relstartime=scheduled,
                        duration=duration,
                        warn=warn_time,
                        alert=alert_time,
                    )  # duration is in minutes
                    logger.debug(
                        f"{sname} has fixed duration {duration} min (without setup/cleanup)"
                    )

                this_equipment = am.selectEquipment(
                    operator=self.operator,
                    service=this_service,
                    model=equipment_model,
                    reqtime=service_scheduled_dt,
                    reqend=service_scheduled_end_dt,
                    use=True,
                )  # this will attach this_equipment to this_service

                if this_equipment is None:
                    return (
                        False,
                        f"FlightServices::service: vehicle not found for {sname}",
                    )

                equipment_startpos = self.airport.selectRandomServiceDepot(sname)
                this_equipment.setPosition(equipment_startpos)

                equipment_endpos = self.airport.selectRandomServiceRestArea(sname)
                this_equipment.setNextPosition(equipment_endpos)

                if equipment_startpos is None or equipment_endpos is None:
                    logger.warning(
                        f"positions: {equipment_startpos} -> {equipment_endpos}"
                    )

                duration2 = this_service.duration()
                if self.flight.load_factor != 1.0:  # Wow
                    logger.debug(
                        f"service {sname}: reduced duration: load factor={self.flight.load_factor}"
                    )
                    duration2 = duration2 * self.flight.load_factor

                duration_str = round(duration2 / 60, 1)
                this_service.setRSTSchedule(
                    relstartime=scheduled,
                    duration=duration_str,
                    warn=warn_time,
                    alert=alert_time,
                )
                logger.debug(
                    f"service {sname}: added RSTS sched={scheduled}, duration={duration_str} min, w={warn_time}, a={alert_time} (with setup/cleanup)"
                )

            logger.debug(f"..adding..")
            s2 = svc.copy()
            s2["service"] = this_service
            self.services.append(s2)
            logger.debug("..done")

        return (True, "FlightServices::service: completed")

    # #######################
    # Moving
    #
    def move(self):
        for service in self.services:
            logger.debug(f"moving {service['type']}..")
            move = ServiceMovement(service["service"], self.airport)
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
            if emit.is_event_service():
                logger.debug(
                    f"service {service[TAR_SERVICE.TYPE.value]} does not need scheduling of positions"
                )
                continue
            logger.debug(f"scheduling {service[TAR_SERVICE.TYPE.value]}..")
            stime = scheduled + timedelta(
                minutes=service[TAR_SERVICE.START.value]
            )  # nb: service["scheduled"] can be negative
            ret = emit.schedule(SERVICE_PHASE.SERVICE_START.value, stime, do_print)
            if not ret[0]:
                return ret
            logger.debug(
                f"there are {len(emit.getScheduledPoints())} scheduled emit points"
            )
            logger.debug(f"..done")
        return (True, "FlightServices::schedule: completed")

    def scheduleMessages(self, scheduled: datetime, do_print: bool = False):
        for service in self.services:
            emit = service["emit"]
            logger.debug(f"scheduling {service[TAR_SERVICE.TYPE.value]}..")
            stime = scheduled + timedelta(
                minutes=service[TAR_SERVICE.START.value]
            )  # nb: service["scheduled"] can be negative
            ret = emit.scheduleMessages(
                SERVICE_PHASE.SERVICE_START.value, stime, do_print
            )
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

        print(f"RELATIVE SERVICE TIME SCHEDULE", file=output)
        PTS_HEADERS = [
            "event",
            "start",
            "duration",
            "warn",
            "alert",
            "start time",
            "warn time",
            "alert time",
            "end time",
            "end warn time",
            "end alert time",
        ]
        table = []
        scheduled = scheduled.replace(microsecond=0)
        for service in self.services:
            s = service["service"]
            line = []
            sty = type(s).__name__.replace("Service", "").lower()
            if sty == EVENT_ONLY_MESSAGE:
                sty = s.label
            line.append(sty)
            line.append(s.rst_schedule.reltime)
            line.append(s.rst_schedule.duration)
            line.append(s.rst_schedule.warn)
            line.append(s.rst_schedule.alert)
            line.append(scheduled + timedelta(minutes=s.rst_schedule.reltime))
            if s.rst_schedule.warn is not None:
                line.append(
                    scheduled
                    + timedelta(minutes=s.rst_schedule.reltime + s.rst_schedule.warn)
                )
            else:
                line.append(None)
            if s.rst_schedule.alert is not None:
                line.append(
                    scheduled
                    + timedelta(minutes=s.rst_schedule.reltime + s.rst_schedule.alert)
                )
            else:
                line.append(None)
            line.append(
                scheduled
                + timedelta(minutes=s.rst_schedule.reltime + s.rst_schedule.duration)
            )
            if s.rst_schedule.warn is not None:
                line.append(
                    scheduled
                    + timedelta(
                        minutes=s.rst_schedule.reltime
                        + s.rst_schedule.duration
                        + s.rst_schedule.warn
                    )
                )
            else:
                line.append(None)
            if s.rst_schedule.alert is not None:
                line.append(
                    scheduled
                    + timedelta(
                        minutes=s.rst_schedule.reltime
                        + s.rst_schedule.duration
                        + s.rst_schedule.alert
                    )
                )
            else:
                line.append(None)
            for i in range(5, 11):
                if line[i] is not None:
                    line[i] = line[i].strftime("%H:%M:%S")
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

        for (
            m
        ) in (
            self.flight.get_movement().getMessages()
        ):  # move.getMessages() includes flight.getMessages()
            line = []
            line.append("move")
            line.append(type(m).__name__)
            line.append(m.getAbsoluteEmissionTime().replace(microsecond=0))
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
                line.append(m.getAbsoluteEmissionTime().replace(microsecond=0))
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
            if emit.is_event_service():
                logger.debug(
                    f"service {service[TAR_SERVICE.TYPE.value]} does not need formatting of positions"
                )
                continue
            logger.debug(
                f"formatting '{service['type']}' ({len(service['emit'].move_points)}, {len(service['emit']._emit_points)}, {len(service['emit'].getScheduledPoints())}).."
            )
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
            logger.debug(
                f"formatting '{service['type']}' ({len(service['emit'].move_points)}, {len(service['emit']._emit_points)}, {len(service['emit'].getScheduledPoints())}).."
            )
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
            if emit.is_event_service():
                logger.debug(
                    f"service {service[TAR_SERVICE.TYPE.value]} does not need enqueueing positions"
                )
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
