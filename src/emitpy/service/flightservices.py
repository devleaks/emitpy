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

logger = logging.getLogger("FlightServices")


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


    def save(self, redis):
        for service in self.services:
            logger.debug(f":save: saving to redis {service['type']}..")
            emit = service["emit"]
            ret = emit.save(redis)
            if not ret[0]:
                return ret
            logger.debug(f":save: ..done")
        return (True, "FlightServices::save: completed")


    def service(self):
        # From dict, make append appropriate service to list
        svcs = self.flight.aircraft.actype.getTurnaroundProfile(move=self.flight.get_move(),
                                                                ramp=self.ramp.getProp("sub-type"))
        if svcs is None:
            return (False, f"FlightServices::run: no turnaround profile for {self.flight.aircraft.actype}")

        am = self.airport.manager

        for svc in svcs:
            sname, sched = list(svc.items())[0]
            logger.debug(f":service: creating service {sname}..")

            service_scheduled_dt = self.flight.scheduled_dt + timedelta(minutes=sched[0])
            service_scheduled_end_dt = self.flight.scheduled_dt + timedelta(minutes=(sched[0]+sched[1]))
            this_service = Service.getService(sname)(scheduled=service_scheduled_dt,
                                                       ramp=self.flight.ramp,
                                                       operator=self.operator)

            duration = sched[1]
            if self.flight.load_factor != 1.0:  # Wow
                duration = duration * self.flight.load_factor

            this_service.setPTS(relstartime=sched[0], duration=duration)
            this_service.setFlight(self.flight)
            this_service.setAircraftType(self.flight.aircraft.actype)
            this_service.setRamp(self.ramp)
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

            logger.debug(f":service: .. adding ..")
            self.services.append({
                "type": sname,
                "service": this_service,
                "scheduled": sched[0],
                "duration": sched[1]
            })
            logger.debug(":service: .. done")

        return (True, "FlightServices::service: completed")


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


    def schedule(self, scheduled: datetime):
        # The scheduled date time recevied should be
        # ONBLOCK time for arrival
        # OFFBLOCK time for departure
        for service in self.services:
            logger.debug(f":schedule: scheduling {service['type']}..")
            stime = scheduled + timedelta(minutes=service["scheduled"])  # nb: service["scheduled"] can be negative
            service["emit"].serviceTime(SERVICE_PHASE.SERVICE_START.value, service["duration"] * 60)  # seconds
            service["emit"].schedule(SERVICE_PHASE.SERVICE_START.value, stime)
            logger.debug(f":schedule: ..done")
        return (True, "FlightServices::schedule: completed")


    def enqueuetoredis(self, queue):
        for service in self.services:
            logger.debug(f":enqueuetoredis: enqueuing '{service['type']}'..")
            formatted = EnqueueToRedis(service["emit"], queue)
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



