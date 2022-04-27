"""
Creates all services required for a flight, depends on ramp and actype.

"""
import logging
from datetime import datetime, timedelta

from .service import Service
from .servicemovement import ServiceMove

from .. import service

from ..flight import Flight
from ..emit import Emit, EnqueueToRedis
from ..constants import SERVICE_PHASE, ARRIVAL, DEPARTURE

logger = logging.getLogger("Turnaround")


class ServiceFlight:

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
        return (True, "ServiceFlight::save: completed")


    def saveDB(self, redis):
        for service in self.services:
            logger.debug(f"saving to redis {service['type']}..")
            emit = service["emit"]
            ret = emit.saveDB(redis)
            if not ret[0]:
                return ret
            logger.debug(f"..done")
        return (True, "ServiceFlight::saveDB: completed")


    def service(self):
        # From dict, make append appropriate service to list
        if self.actype.tarprofile is None:
            logger.warning(":run: no turnaround profile")
            return (False, "ServiceFlight::run: no turnaround profile")

        move = ARRIVAL if self.flight.is_arrival() else DEPARTURE
        if not move in self.flight.aircraft.actype.tarprofile:
            return (False, f"ServiceFlight::run: no turnaround profile for {move}")

        svcs = self.flight.aircraft.actype.tarprofile[move]

        for svc in svcs:
            sname, sched = list(svc.items())[0]

            logger.debug(f"creating service {sname}..")
            this_service = Service.getService(sname)(operator=self.operator, quantity=0)

            this_service.setRamp(self.flight.ramp)
            this_service.setAircraftType(self.flight.aircraft.actype)
            vehicle_model = sched[2] if len(sched) > 2 else None
            this_vehicle = self.airport.manager.selectServiceVehicle(operator=self.operator,
                                                                     service=this_service,
                                                                     model=vehicle_model,
                                                                     reqtime=self.flight.scheduled_dt)

            if this_vehicle is None:
                return (True, f"ServiceFlight::service: vehicle not found")

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
            #     "move": move,
                "scheduled": sched[0],
                "duration": sched[1]
            })
            logger.debug(".. done")

        return (True, "ServiceFlight::service: completed")


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
        return (True, "ServiceFlight::move: completed")


    def emit(self, emit_rate: int):
        for service in self.services:
            logger.debug(f"emitting {service['type']}..")
            emit = Emit(service["move"])
            ret = emit.emit(emit_rate)
            if not ret[0]:
                return ret
            service["emit"] = emit
            logger.debug(f"..done")
        return (True, "ServiceFlight::emit: completed")


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
        return (True, "ServiceFlight::schedule: completed")


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
        return (True, "ServiceFlight::enqueuetoredis: completed")



