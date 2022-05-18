"""
A Service  is a maintenance operation performed on an aircraft during a turn-around.

"""
import sys
import logging
from datetime import datetime

from emitpy.constants import SERVICE, ID_SEP
from emitpy.utils import key_path
from .servicevehicle import ServiceVehicle

logger = logging.getLogger("Service")


class PTSTime:

    def __init__(self, ref_scheduled: datetime, scheduled: int, duration: int):

        self.pts_reltime     = scheduled  # relative scheduled service date/time in minutes after/before(negative) on-block/off-block
        self.pts_duration    = duration   # relative scheduled service duration in minutes, may be refined and computed from quantity+vehicle
        self.pts_scheduled   = None  # absolute time for above
        self.pts_estimated   = None
        self.pts_actual_start = None
        self.pts_actual_end   = None

    def getStartEndTimes(self, timetype: str = "scheduled"):
        if timetype == "actual":
            return (self.pts_actual_start, self.pts_actual_end)
        if timetype == "estimated" and self.pts_estimated is not None:
            return (self.pts_estimated + timedelta(minutes=self.pts_reltime),
                    self.pts_estimated + timedelta(minutes=(self.pts_reltime + sepf.pts_duration)))
        return (self.pts_scheduled + timedelta(minutes=self.pts_reltime),
                self.pts_scheduled + timedelta(minutes=(self.pts_reltime + sepf.pts_duration)))


class GroundSupport:

    def __init__(self, operator: "Company", scheduled: int = 0, duration: int = 0):
        self.operator = operator

        self.pts_reltime     = scheduled  # relative scheduled service date/time in minutes after/before(negative) on-block/off-block
        self.pts_duration    = duration   # relative scheduled service duration in minutes, may be refined and computed from quantity+vehicle
        self.pts_scheduled   = None  # absolute time for above
        self.pts_estimated   = None
        self.pts_actual      = None

        self.scheduled = None  # scheduled service date/time = pts_refscheduled + pts_scheduled
        self.estimated = None
        self.actual = None
        self.actual_end = None
        self.schedule_history = []

        self.pause_before = 0  # currently unused
        self.pause_after = 0   # currently unused
        self.setup_time = 0    # currently unused
        self.close_time = 0    # currently unused

        self.vehicle = None
        self.next_position = None
        self.route = []
        self.name = None

    def getId(self):
        return self.name

    def getInfo(self):
        return {
            "ground-support": type(self).__name__,
            "operator": self.operator.getInfo(),
            "schedule": self.pts_schedule,
            "duration": self.pts_duration,
            "name": self.name
        }

    def getScheduleHistory(self):
        return self.schedule_history

    def setPTS(self, scheduled: int, duration: int):
        self.pts_scheduled = scheduled
        self.pts_duration  = duration

    def setName(self, name: str):
        self.name = name

    def setVehicle(self, vehicle: ServiceVehicle):
        self.vehicle = vehicle

    def setNextPosition(self, position):
        self.pos_next = position

    def duration(self, dflt: int = 30 * 60):
        if self.vehicle is None:
            return dflt
        return self.vehicle.service_duration(self.quantity)

    def run(self, moment: datetime):
        return (False, "Service::run not implemented")

    def setEstimatedTime(self, dt: datetime, info_time: datetime = datetime.now()):
        self.estimated = dt
        self.schedule_history.append((info_time.isoformat(), "ET", dt.isoformat()))

    def setActualTime(self, dt: datetime, info_time: datetime = datetime.now()):
        self.actual = dt
        self.schedule_history.append((info_time.isoformat(), "AT", dtv))

    def started(self, dt: datetime, info_time: datetime = datetime.now()):
        self.setActualTime(dt, info_time)

    def terminated(self, dt: datetime, info_time: datetime = datetime.now()):
        self.actual_end = dt
        self.schedule_history.append((info_time.isoformat(), "TT", dt.isoformat()))  # Terminated Time


class Service(GroundSupport):

    def __init__(self, scheduled: datetime, ramp: "Ramp", operator: "Company", quantity: float = 1):
        GroundSupport.__init__(self, operator=operator)
        self.scheduled = scheduled
        self.quantity = quantity
        self.ramp = ramp
        self.actype = None
        self.flight = None  # If this particular service is part of a larger coordinated set for a flight
        self.turnaround = None  # If this particular service is part of a larger coordinated set for a pair of flights

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
        """
        A service is identified by its type, at a given ramp, at a give time.
        Since several such services can be planned, we add the vehicle as a discriminent.
        """
        r = self.ramp.getName() if self.ramp is not None else "noramp"
        s = self.scheduled.isoformat().replace(":", ".") if self.scheduled is not None else "noschedule"
        v = self.vehicle.getId() if self.vehicle is not None else "novehicle"
        return key_path(type(self).__name__, r, s, v)

    def getInfo(self):
        return {
            "service-type": type(self).__name__,
            "service-identifier": self.getId(),
            "operator": self.operator.getInfo(),
            "ramp": self.ramp.getInfo(),
            "vehicle": self.vehicle.getInfo(),
            "icao24": self.vehicle.icao24,
            "registration": self.vehicle.registration,
            "scheduled": self.scheduled.isoformat(),
            "quantity": self.quantity
        }

    def getKey(self):
        return key_path(REDIS_DATABASE.SERVICES.value, self.getId())

    def __str__(self):
        s = type(self).__name__
        s = s + " at ramp " + self.ramp.getName()
        s = s + " by vehicle " + self.vehicle.getName()  # model, icao24

    def setAircraftType(self, actype: "AircraftType"):
        self.actype = actype

    def setRamp(self, ramp: "Ramp"):
        self.ramp = ramp

    def setFlight(self, flight: "Flight"):
        self.flight = flight

    def setTurnaround(self, turnaround: "Turnaround"):
        self.turnaround = turnaround


# ########################@
# Specific ground handling services
#
#
class CleaningService(Service):

    def __init__(self, scheduled: datetime, ramp: "Ramp", operator: "Company", quantity: float = 1):
        Service.__init__(self, scheduled=scheduled, ramp=ramp, operator=operator, quantity=quantity)


class SewageService(Service):

    def __init__(self, scheduled: datetime, ramp: "Ramp", operator: "Company", quantity: float = 1):
        Service.__init__(self, scheduled=scheduled, ramp=ramp, operator=operator, quantity=quantity)


class CateringService(Service):

    def __init__(self, scheduled: datetime, ramp: "Ramp", operator: "Company", quantity: float = 1):
        Service.__init__(self, scheduled=scheduled, ramp=ramp, operator=operator, quantity=quantity)


class WaterService(Service):

    def __init__(self, scheduled: datetime, ramp: "Ramp", operator: "Company", quantity: float = 1):
        Service.__init__(self, scheduled=scheduled, ramp=ramp, operator=operator, quantity=quantity)


class FuelService(Service):

    def __init__(self, scheduled: datetime, ramp: "Ramp", operator: "Company", quantity: float = 1):
        Service.__init__(self, scheduled=scheduled, ramp=ramp, operator=operator, quantity=quantity)


class CargoService(Service):

    def __init__(self, scheduled: datetime, ramp: "Ramp", operator: "Company", quantity: float = 1):
        Service.__init__(self, scheduled=scheduled, ramp=ramp, operator=operator, quantity=quantity)


class BaggageService(Service):

    def __init__(self, scheduled: datetime, ramp: "Ramp", operator: "Company", quantity: float = 1):
        Service.__init__(self, scheduled=scheduled, ramp=ramp, operator=operator, quantity=quantity)

