"""
Creates all services required for a flight, depends on movement, ramp, and actype.
"""
import logging
from datetime import datetime, timedelta

from .service import Service
from .servicemovement import ServiceMove

import emitpy.service

from emitpy.flight import Flight
from emitpy.emit import Emit, EnqueueToRedis
from emitpy.constants import SERVICE_PHASE, ARRIVAL, DEPARTURE

logger = logging.getLogger("Turnaround")


class FlightServices:

    def __init__(self, flight: Flight, operator: "Company"):
        self.flight = flight
        self.operator = operator
        self.ramp = flight.ramp  # should check that aircraft was not towed to another ramp for departure.
        self.actype = flight.aircraft.actype
        self.services = []
        self.airport = None

    def setManagedAirport(self, airport):
        self.airport = airport


    def save(self):
        for service in self.services:
            logger.debug(f"saving {service['type']}..")
            emit = service["emit"]
            ret = emit.save()
            if not ret[0]:
                return ret
            logger.debug(f"..done")
        return (True, "FlightServices::save: completed")


    def save(self, redis):
        for service in self.services:
            logger.debug(f"saving to redis {service['type']}..")
            emit = service["emit"]
            ret = emit.save(redis)
            if not ret[0]:
                return ret
            logger.debug(f"..done")
        return (True, "FlightServices::save: completed")


    def service(self):
        # From dict, make append appropriate service to list
        if self.actype.tarprofile is None:
            logger.warning(":run: no turnaround profile")
            return (False, "FlightServices::run: no turnaround profile")

        move = ARRIVAL if self.flight.is_arrival() else DEPARTURE
        if not move in self.flight.aircraft.actype.tarprofile:
            return (False, f"FlightServices::run: no turnaround profile for {move}")

        svcs = self.flight.aircraft.actype.tarprofile[move]
        am = self.airport.manager

        for svc in svcs:
            sname, sched = list(svc.items())[0]
            logger.debug(f"creating service {sname}..")

            service_scheduled_dt = self.flight.scheduled_dt + timedelta(minutes=sched[0])
            service_scheduled_end_dt = self.flight.scheduled_dt + timedelta(minutes=(sched[0]+sched[1]))
            this_service = Service.getService(sname)(scheduled=service_scheduled_dt,
                                                       ramp=self.flight.ramp,
                                                       operator=self.operator)
            this_service.setPTS(scheduled=sched[0], duration=sched[1])
            this_service.setFlight(self.flight)
            this_service.setAircraftType(self.flight.aircraft.actype)
            vehicle_model = sched[2] if len(sched) > 2 else None
            # should book vehicle a few minutes before and after...
            this_vehicle = am.selectServiceVehicle(operator=self.operator,
                                                   service=this_service,
                                                   model=vehicle_model,
                                                   reqtime=service_scheduled_dt,
                                                   reqend=service_scheduled_end_dt,
                                                   use=True)

            if this_vehicle is None:
                return (True, f"FlightServices::service: vehicle not found")

            vehicle_startpos = self.airport.selectRandomServiceDepot(sname)
            this_vehicle.setPosition(vehicle_startpos)

            vehicle_endpos = self.airport.selectRandomServiceRestArea(sname)
            this_vehicle.setNextPosition(vehicle_endpos)

            # logger.debug(".. moving ..")
            # move = ServiceMove(this_service, self.airport)
            # move.move()
            # move.save()

            logger.debug(f".. adding ..")
            self.services.append({
                "type": sname,
                "service": this_service,
                "scheduled": sched[0],
                "duration": sched[1]
            })
            logger.debug(".. done")

        return (True, "FlightServices::service: completed")


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


    def schedule(self, scheduled: datetime):
        # The scheduled date time recevied should be
        # ONBLOCK time for arrival
        # OFFBLOCK time for departure
        for service in self.services:
            logger.debug(f"scheduling {service['type']}..")
            stime = scheduled + timedelta(minutes=service["scheduled"])  # nb: service["scheduled"] can be negative
            service["emit"].serviceTime(SERVICE_PHASE.SERVICE_START.value, service["duration"] * 60)  # seconds
            service["emit"].schedule(SERVICE_PHASE.SERVICE_START.value, stime)
            logger.debug(f"..done")
        return (True, "FlightServices::schedule: completed")


    def enqueuetoredis(self, queue):
        for service in self.services:
            logger.debug(f"enqueuing to redis {service['type']}..")
            formatted = EnqueueToRedis(service["emit"], queue)
            ret = formatted.format()
            if not ret[0]:
                return ret
            ret = formatted.save()
            if not ret[0] and ret[1] != "EnqueueToRedis::save key already exist":
                return ret
            ret = formatted.enqueue()
            if not ret[0]:
                return ret
            logger.debug(f"..done")
        return (True, "FlightServices::enqueuetoredis: completed")



