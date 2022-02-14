"""
A Turnaround is a collection of Services to be performed on an aircraft during a turn-around.

"""
import logging
from datetime import datetime

from .service import Service

from .. import service

from ..flight import Flight

logger = logging.getLogger("Turnaround")


class Turnaround:

    def __init__(self, arrival: Flight, departure: Flight):
        self.arrival = arrival
        self.departure = departure
        self.managedAirport = None
        self.services = {}
        self.ramp = arrival.ramp  # should check that aircraft was not towed to another ramp for departure.
        self.gse_pois = None      # If it is the case, we can schedule towing :-)!
        self.aircraft = arrival.aircraft
        self.actype = arrival.aircraft.actype


    def setManagedAirport(self, airport):
        self.managedAirport = airport


    def plan(self):
        # From dict, make append appropriate service to list
        if self.actype.tarraw is None:
            logger.warning(":plan: no turnaround profile")
            return (False, "Turnaround::plan: no turnaround profile")

        svcs = self.actype.tarraw["services"]
        for s in svcs:
            # https://stackoverflow.com/questions/3061/calling-a-function-of-a-module-by-using-its-name-a-string
            for st in s:
                cn = st + "Service"
                if hasattr(service, cn):
                    svc = getattr(service, cn)(s[st][0], s[st][1])  ## getattr(sys.modules[__name__], str) if same module...
                    svc.setTurnaround(self)
                    self.services[st] = svc
                    logger.debug(":plan: added %s(schedule=%d, duration=%d)" % (type(svc).__name__, svc.schedule, svc.duration))
                else:
                    logger.warning(":plan: service %s not found" % (cn))

        return (True, "Turnaround::plan: planned")


    def make(self):
        if self.actype.gseraw is None:
            logger.warning(":plan: no support equipment profile")
            return (False, "Turnaround::plan: no support equipment profile")

        logger.debug(":make:ramp is %s" % (self.ramp.getProp("name")))

        if len(self.ramp.service_pois) == 0:
            status = self.ramp.makeServicePOIs(self.actype.gseraw)
            if not status[0]:
                return status
            else:
                logger.debug(":make:create service points %s" % (self.ramp.service_pois.keys()))

        for name, svc in self.services.items():
            logger.debug(":make: doing %s .." % name)
            svc.make(self.managedAirport)
            logger.debug(":make: %s ..done" % name)

        return (True, "Turnaround::make: made")


    def run(self, moment: datetime):
        for name, svc in self.services.items():
            logger.debug(":run: running %s .." % name)
            svc.run(moment)
            logger.debug(":run: %s ..done" % name)

        return (True, "Turnaround::run ran")


    def setVehicle(self, service, vehicle):
        if service in self.services.keys():
            self.services[service].setVehicle(vehicle)