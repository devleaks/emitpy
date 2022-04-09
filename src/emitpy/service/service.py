"""
A Service  is a maintenance operation performed on an aircraft during a turn-around.

"""
import sys
import logging
import random
from datetime import datetime

from .servicevehicle import ServiceVehicle
from ..geo import FeatureWithProps, printFeatures, asLineString
from ..graph import Route
from ..constants import SERVICE

logger = logging.getLogger("Service")


class Service:

    def __init__(self, operator: "Company", quantity: float):
        self.operator = operator
        self.quantity = quantity
        self.schedule = None      # scheduled service date/time in minutes after/before(negative) on-block
        self.duration = None      # scheduled duration in minutes, will be different from actual duration
        self.ramp = None
        self.actype = None
        self.turnaround = None
        self.vehicle = None
        self.starttime = None
        self.next_position = None
        self.route = []

    @staticmethod
    def getService(service: str):
        mod = sys.modules[__name__]
        cn = service[0].upper() + service[1:].lower() + "Service"  # @todo: Hum.
        if hasattr(mod, cn):
            svc = getattr(sys.modules[__name__], cn)  # same module...
            logger.debug(f":getService: returning {cn}")
            return svc
        logger.warning(f":getService: service {cn} not found")
        return None


    @staticmethod
    def getCombo():
        a = []
        for s in SERVICE:
            a.append((s.value, s.value[0].upper()+s.value[1:]))
        return a


    def getId(self):
        return type(self).__name__ + ":" + self.getShortId()


    def getShortId(self):
        r = self.ramp.getProp("name") if self.ramp is not None else "noramp"
        v = self.vehicle.getId() if self.vehicle is not None else "novehicle"
        return r + ":" + v


    def getInfo(self):
        return {
            "service-type": type(self).__name__,
            "service-identifier": self.getId(),
            "operator": self.operator.getInfo(),
            "ramp": self.ramp.getInfo(),
            "vehicle": self.vehicle.getInfo(),
            "icao24": self.vehicle.icao24,
            "registration": self.vehicle.registration
        }


    def __str__(self):
        s = type(self).__name__
        s = s + " at ramp " + self.ramp.getProp("name")
        s = s + " by vehicle " + self.vehicle.getProp("name")  # model, icao24


    def setTurnaround(self, turnaround: "Turnaround"):
        self.turnaround = turnaround


    def setAircraftType(self, actype: "AircraftType"):
        self.actype = actype


    def setRamp(self, ramp: "Ramp"):
        self.ramp = ramp


    def setVehicle(self, vehicle: ServiceVehicle):
        self.vehicle = vehicle


    def setNextPosition(self, position):
        self.pos_next = position


    def serviceDuration(self):
        return self.vehicle.service_duration(self.quantity)


    def run(self, moment: datetime):
        return (False, "Service::run not implemented")


class CleaningService(Service):

    def __init__(self, operator: "Company", quantity: float):
        Service.__init__(self, operator=operator, quantity=quantity)


class SewageService(Service):

    def __init__(self, operator: "Company", quantity: float):
        Service.__init__(self, operator=operator, quantity=quantity)


class CateringService(Service):

    def __init__(self, operator: "Company", quantity: float):
        Service.__init__(self, operator=operator, quantity=quantity)


class WaterService(Service):

    def __init__(self, operator: "Company", quantity: float):
        Service.__init__(self, operator=operator, quantity=quantity)


class FuelService(Service):

    def __init__(self, operator: "Company", quantity: float):
        Service.__init__(self, operator=operator, quantity=quantity)


class CargoService(Service):

    def __init__(self, operator: "Company", quantity: float):
        Service.__init__(self, operator=operator, quantity=quantity)


class BaggageService(Service):

    def __init__(self, operator: "Company", quantity: float):
        Service.__init__(self, operator=operator, quantity=quantity)

