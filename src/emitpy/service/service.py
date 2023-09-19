"""
A Service  is a maintenance operation performed on an aircraft during a turn-around.

"""
import sys
import logging
from datetime import datetime, timezone
from typing import Union
from types import NoneType

from emitpy.constants import FLIGHT_TIME_FORMAT, SERVICE, ID_SEP, REDIS_DATABASE
from emitpy.utils import key_path
from .ground_support import GroundSupport

logger = logging.getLogger("Service")


class Service(GroundSupport):

    def __init__(self, scheduled: datetime, ramp: "Ramp", operator: "Company", quantity: float = None):
        GroundSupport.__init__(self, operator=operator)
        self.scheduled = scheduled
        self.quantity = quantity  # Size of service, that will define duration. Vehicle set the speed of processing quantity (flow)
        self.ramp = ramp
        self.actype = None
        self.flight = None  # If this particular service is part of a larger coordinated set for a flight
        self.turnaround = None  # If this particular service is part of a larger coordinated set for a pair of flights
        self._cached_duration = None

    @staticmethod
    def getService(service: str):
        mod = sys.modules[__name__]
        cn = service[0].upper() + service[1:].lower() + "Service"  # @todo: Hum.
        if hasattr(mod, cn):
            svc = getattr(sys.modules[__name__], cn)  # same module...
            logger.debug(f"returning {cn}")
            return svc
        logger.warning(f"service {cn} not found")
        return None

    @staticmethod
    def getServiceName(service_class):
        service_str = type(service_class).__name__ if isinstance(service_class, Service) else service_class
        return service_str.replace("Service", "").lower()

    @staticmethod
    def getCombo():
        a = []
        for s in SERVICE:
            a.append((s.value, s.value[0].upper()+s.value[1:]))
        return a

    @staticmethod
    def parseId(service_id):
        # returns (service name, ramp, scehduled time, vehicle identifier)
        a = service_id.split(ID_SEP)
        # if len(a) > 0:
        #     a[0] = a[0].replace("Service", "").lower()
        if len(a) > 3:
            dt = a[2]
            a[2] = datetime.strptime(dt, FLIGHT_TIME_FORMAT).replace(tzinfo=timezone.utc)
        return a

    def getId(self):
        """
        A service is identified by its type, at a given ramp, at a give time.
        Since several such services can be planned, we add the vehicle as a discriminent.
        """
        r = self.ramp.getName() if self.ramp is not None else "noramp"
        s = self.scheduled.astimezone(tz=timezone.utc).strftime(FLIGHT_TIME_FORMAT) if self.scheduled is not None else "noschedule"
        v = self.vehicle.getId() if self.vehicle is not None else "novehicle"
        if self.ramp is None:
            logger.warning(f"service on ramp {r} at {s} with vehicle {v} as no ramp")
        if self.scheduled is None:
            logger.warning(f"service on ramp {r} at {s} with vehicle {v} as no schedule")
        # if self.vehicle is None:
        #     logger.warning(f"service on ramp {r} at {s} with vehicle {v} as no vehicle")
        return key_path(type(self).__name__, r, s, v)

    def getInfo(self):
        return {
            "ground-support": super().getInfo(),  # contains PTS, etc.
            "service-type": type(self).__name__,
            "service-identifier": self.getId(),
            "operator": self.operator.getInfo(),
            "ramp": self.ramp.getInfo(),
            "vehicle": self.vehicle.getInfo() if self.vehicle is not None else "novehicle",
            "icao24": self.vehicle.icao24 if self.vehicle is not None else "novehicle",
            "registration": self.vehicle.registration if self.vehicle is not None else "novehicle",
            "scheduled": self.scheduled.isoformat(),
            "quantity": self.quantity,
            "flight": self.flight.getId() if self.flight is not None else None
        }

    def getKey(self):
        return key_path(REDIS_DATABASE.SERVICES.value, self.getId())

    def __str__(self):
        s = type(self).__name__
        s = s + " at ramp " + self.ramp.getName()
        s = s + " by vehicle " + self.vehicle.getName()  # model, icao24

    def is_arrival(self) -> Union[bool, NoneType]:
        """
        Returns True if service is for an arrival flight, False if service is for a departure,
        or None if service is independent.
        """
        if self.flight is not None:
            return self.flight.is_arrival()
        return None

    def setAircraftType(self, actype: "AircraftType"):
        self.actype = actype

    def setRamp(self, ramp: "Ramp"):
        self.ramp = ramp

    def setQuantity(self, quantity: float):
        self.quantity = quantity

    def setFlight(self, flight: "Flight"):
        self.flight = flight

    def setTurnaround(self, turnaround: "Turnaround"):
        self.turnaround = turnaround

    def is_event(self) -> bool:
        return False

    def using_quantity(self) -> bool:
        return self.quantity is not None and self.vehicle is not None

    def duration(self, add_setup: bool = False):  # default is half an hour
        # returns service duration in seconds
        if self.quantity is not None:
            logger.debug(f"{self.getId()}: using quantity ({self.quantity})")
            return self.compute_duration(add_setup)

        if self.rst_schedule.duration is not None:
            service = self.rst_schedule.duration * 60
            setup_cleanup = 0
            if add_setup and self.vehicle is not None:
                setup_cleanup = self.vehicle.service_duration(quantity=0, add_setup=True)
                logger.debug(f"{self.getId()}: service={service}, setup/cleanup={setup_cleanup}, total={service+setup_cleanup}")
            else:
                logger.debug(f"{self.getId()}: service={service}, no setup/cleanup")
            return service+setup_cleanup
        logger.warning(f"{self.getId()}: no quantity or no duration, service takes no time")
        return 0

    def compute_duration(self, add_setup: bool = False):
        if self.quantity is not None and self.vehicle is not None:
            flow = self.vehicle.flow
            duration = self.vehicle.service_duration(quantity=self.quantity, add_setup=False)
            setup_cleanup = self.vehicle.service_duration(quantity=0, add_setup=True)
            logger.debug(f"{self.getId()}: quantity ({self.quantity}) x vehicle {self.vehicle.getId()} flow ({flow}) => duration {duration} (setup/cleanup={setup_cleanup})")
            return duration + setup_cleanup if add_setup else duration
        if self.rst_schedule.duration is not None:
            logger.warning(f"{self.name}: no quantity or no vehicle, using service fixed duration")
            return self.rst_schedule.duration * 60  # seconds
        logger.warning(f"{self.name}: no quantity or no vehicle, no fixed duration, service takes no time")
        return 0

# ########################
# Specific ground handling services
#
#
# Message Only Service (no vehicle movement)
#
class EventService(Service):

    def __init__(self, scheduled: datetime, ramp: "Ramp", operator: "Company", quantity: float = None):
        Service.__init__(self, scheduled=scheduled, ramp=ramp, operator=operator, quantity=quantity)

    def is_event(self) -> bool:
        return True

# PAX
#
class PassengerService(Service):

    def __init__(self, scheduled: datetime, ramp: "Ramp", operator: "Company", quantity: float = None):
        Service.__init__(self, scheduled=scheduled, ramp=ramp, operator=operator, quantity=quantity)

# ARRIVAL
#
class CleaningService(Service):

    def __init__(self, scheduled: datetime, ramp: "Ramp", operator: "Company", quantity: float = None):
        Service.__init__(self, scheduled=scheduled, ramp=ramp, operator=operator, quantity=quantity)

class SewageService(Service):

    def __init__(self, scheduled: datetime, ramp: "Ramp", operator: "Company", quantity: float = None):
        Service.__init__(self, scheduled=scheduled, ramp=ramp, operator=operator, quantity=quantity)

# DEPARTURE
#
class CateringService(Service):

    def __init__(self, scheduled: datetime, ramp: "Ramp", operator: "Company", quantity: float = None):
        Service.__init__(self, scheduled=scheduled, ramp=ramp, operator=operator, quantity=quantity)

class WaterService(Service):

    def __init__(self, scheduled: datetime, ramp: "Ramp", operator: "Company", quantity: float = None):
        Service.__init__(self, scheduled=scheduled, ramp=ramp, operator=operator, quantity=quantity)

class FuelService(Service):

    def __init__(self, scheduled: datetime, ramp: "Ramp", operator: "Company", quantity: float = None):
        Service.__init__(self, scheduled=scheduled, ramp=ramp, operator=operator, quantity=quantity)

# BOTH
#
class CargoService(Service):

    def __init__(self, scheduled: datetime, ramp: "Ramp", operator: "Company", quantity: float = None):
        Service.__init__(self, scheduled=scheduled, ramp=ramp, operator=operator, quantity=quantity)

class BaggageService(Service):

    def __init__(self, scheduled: datetime, ramp: "Ramp", operator: "Company", quantity: float = None):
        Service.__init__(self, scheduled=scheduled, ramp=ramp, operator=operator, quantity=quantity)

class AircraftService(Service):

    def __init__(self, scheduled: datetime, ramp: "Ramp", operator: "Company", quantity: float = None):
        Service.__init__(self, scheduled=scheduled, ramp=ramp, operator=operator, quantity=quantity)

