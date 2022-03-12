"""
A Service  is a maintenance operation performed on an aircraft during a turn-around.

"""
import logging
import random
from datetime import datetime

from .servicevehicle import ServiceVehicle
from ..geo import FeatureWithProps, printFeatures, asLineString
from ..graph import Route

logger = logging.getLogger("Service")


class Service:

    def __init__(self, operator: "Company", quantity: float):
        self.operator = operator
        self.quantity = quantity
        self.schedule = None      # scheduled service date/time in minutes after/before(negative) on-block
        self.duration = None      # scheduled duration in minutes, will be different from actual duration
        self.ramp = None
        self.flight = None
        self.actype = None
        self.turnaround = None
        self.vehicle = None
        self.starttime = None
        self.next_position = None
        self.route = []

    def getId(self):
        r = self.ramp.getProp("name") if self.ramp is not None else "noramp"
        v = self.vehicle.getId() if self.vehicle is not None else "novehicle"
        return type(self).__name__ + "-" + v + "-" + r

    def getInfo(self):
        return {
            "operator": self.operator.getInfo(),
            "ramp": self.ramp.getInfo(),
            "vehicle": self.vehicle.getInfo(),
            "icao24": self.vehicle.icao24,
            "ident": self.vehicle.registration
        }

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
        if len(self.route) == 0:
            logger.warning(f":run: {type(self).__name__}: no movement")
            return (False, "Service::run no vehicle")
        self.starttime = moment
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

