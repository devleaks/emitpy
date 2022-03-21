"""
A Turnaround is a collection of Services to be performed on an aircraft during a turn-around.

"""
import logging
from datetime import datetime

from .service import Service

from .. import service

from ..flight import Flight

logger = logging.getLogger("Turnaround")


class ServiceFlight:

    def __init__(self, flight: Flight):
        self.flight = flight
        self.ramp = flight.ramp  # should check that aircraft was not towed to another ramp for departure.
        self.aircraft = flight.aircraft
        self.actype = flight.aircraft.actype
        self.managedAirport = None
        self.services = []


    def setManagedAirport(self, airport):
        self.managedAirport = airport


    def addService(self, service: "Service"):
        self.services.append(service)


    def run(self):
        # From dict, make append appropriate service to list
        if self.actype.tarprofile is None:
            logger.warning(":run: no turnaround profile")
            return (False, "Turnaround::run: no turnaround profile")

        move = "arrival" if self.flight.is_arrival() else "departure"
        svcs = self.actype.tarprofile[move]
        for s in svcs:
            # https://stackoverflow.com/questions/3061/calling-a-function-of-a-module-by-using-its-name-a-string
            for st in s:
                cn = st + "Service"
                if hasattr(service, cn):
                    svc = getattr(service, cn)(s[st][0], s[st][1])  ## getattr(sys.modules[__name__], str) if same module...
                    self.services.append(svc)
                    logger.debug(":run: added %s(schedule=%d, duration=%d)" % (type(svc).__name__, svc.schedule, svc.duration))
                else:
                    logger.warning(f":run: service {cn} not found")

        return (True, "Turnaround::run: planned")
