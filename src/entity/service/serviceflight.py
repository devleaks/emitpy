"""
Creates all services required for a flight, depends on ramp and actype.

"""
import logging
from datetime import datetime

from .service import Service
from .servicemovement import ServiceMove

from .. import service

from ..flight import Flight
from ..emit import Emit

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

    def service(self):
        # From dict, make append appropriate service to list
        if self.actype.tarprofile is None:
            logger.warning(":run: no turnaround profile")
            return (False, "Turnaround::run: no turnaround profile")

        move = "arrival" if self.flight.is_arrival() else "departure"
        svcs = self.flight.aircraft.actype.tarprofile[move]

        for svc in svcs:
            sname, sched = list(svc.items())[0]

            logger.debug(f"creating service {sname}..")
            this_service = Service.getService(sname)(operator=self.operator, quantity=0)

            this_service.setRamp(self.flight.ramp)
            this_service.setAircraftType(self.flight.aircraft.actype)
            this_vehicle = self.airport.manager.selectServiceVehicle(operator=self.operator, service=this_service)
            if this_vehicle is None:
                return {
                    "errno": 512,
                    "errmsg": f"service: vehicle not found",
                    "data": None
                }

            vehicle_startpos = self.airport.selectRandomServiceDepot(sname)
            this_vehicle.setPosition(vehicle_startpos)

            vehicle_endpos = self.airport.selectRandomServiceRestArea(sname)
            this_service.setNextPosition(vehicle_endpos)

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


        return (True, "Turnaround::run: completed")


    def move(self):
        for service in self.services:
            logger.debug(f"moving {service['type']}..")
            move = ServiceMove(service["service"], self.airport)
            move.move()
            service["move"] = move
            logger.debug(f"..done")


    def emit(self):
        for service in self.services:
            logger.debug(f"emitting {service['type']}..")
            emit = Emit(service["move"])
            emit.emit()
            emit.saveDB()
            service["emit"] = emit
            logger.debug(f"..done")


