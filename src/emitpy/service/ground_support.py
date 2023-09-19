"""
Ground Support is the base calass for Mission and Service
"""
import logging
from datetime import datetime, timedelta

from .equipment import Equipment
from emitpy.message import Messages

logger = logging.getLogger("GroundSupport")

DEFAULT_DURATION_MINUTES = 30

class RSTSchedule:
    # Relative service time schedule

    def __init__(self, scheduled: int, duration: int, warn: int = None, alert: int = None, label: str = None):

        self.label = label              # Text to remember purpose

        self.reltime      = scheduled  # relative scheduled service date/time in minutes after/before(negative) on-block/off-block
        self.duration     = duration   # relative scheduled service duration in minutes, may be refined and computed from quantity+vehicle

        self.scheduled    = None       # absolute time for above
        self.estimated    = None
        self.actual_start = None
        self.actual_end   = None

        self.warn         = warn
        self.alert        = alert

    def getInfo(self):
        return {
            "label": self.label,
            "start": self.reltime,
            "duration": self.duration,
            "warn": self.warn,
            "alert": self.alert
        }

    def getStartEndTimes(self, timetype: str = "scheduled"):
        if timetype == "actual":
            return (self.actual_start, self.actual_end)
        if timetype == "estimated" and self.estimated is not None:
            return (self.estimated + timedelta(minutes=self.reltime),
                    self.estimated + timedelta(minutes=(self.reltime + self.duration)))
        return (self.scheduled + timedelta(minutes=self.reltime),
                self.scheduled + timedelta(minutes=(self.reltime + self.duration)))

    def getWarnAlertTimes(self, timetype: str = "scheduled"):
        if timetype == "actual":
            return (self.actual_start + timedelta(minutes=self.warn), self.actual_start + timedelta(minutes=self.alert))
        if timetype == "estimated" and self.estimated is not None:
            return (self.estimated + timedelta(minutes=self.warn), self.estimated + timedelta(minutes=self.alert))
        return (self.scheduled + timedelta(minutes=self.warn),
                self.scheduled + timedelta(minutes=self.alert))


class GroundSupport(Messages):

    def __init__(self, operator: "Company", scheduled: int = 0, duration: int = 0, **kwargs):
        Messages.__init__(self)

        self.name = None
        self.label = None

        self.operator = operator

        self.rst_schedule = RSTSchedule(scheduled=scheduled,
                                        duration=duration,
                                        warn=kwargs.get("warn"),
                                        alert=kwargs.get("alert"),
                                        label=kwargs.get("label"))

        self.scheduled   = None
        self.scheduled_dt = None
        self.estimated   = None
        self.estimated_dt = None
        self.actual = None
        self.actual_end = None

        self.pause_before = 0    # currently unused, ideal is to have vehicle go on parking next to ac before
        self.pause_after = 0     # currently unused, ideal is to have vehicle go on parking next to ac after
        self.setup_time = 0      # currently unused, wait between arrival et service position and start of service
        self.cleanup_time = 0    # currently unused, wait between end of service and departure from service position

        self.vehicle = None
        self.next_position = None  # where the vehicle will go after servicing this one
        self.route = []


    def getId(self):
        return self.name

    def getInfo(self):
        return {
            "ground-support": type(self).__name__,
            "operator": self.operator.getInfo(),
            "schedule": self.rst_schedule.getInfo(),
            "name": self.name,
            "label": self.label
        }

    def setRSTSchedule(self, relstartime: int, duration: int, warn: int = None, alert: int = None):
        self.rst_schedule.reltime   = relstartime
        self.rst_schedule.duration  = int(duration)
        if warn is not None:
            self.rst_schedule.warn = warn
        if alert is not None:
            self.rst_schedule.alert = alert

    def setName(self, name: str):
        self.name = name

    def setLabel(self, label: str):
        self.label = label
        self.rst_schedule.label = label

    def setVehicle(self, vehicle: Equipment):
        self.vehicle = vehicle

    def setNextPosition(self, position):
        self.next_position = position

    def duration(self, dflt: int = DEFAULT_DURATION_MINUTES * 60):
        if self.rst_schedule.duration is not None:
            return self.rst_schedule.duration * 60  # seconds
        return dflt

    def compute_duration(self, dflt: int = DEFAULT_DURATION_MINUTES * 60):
        return self.duration(dflt)

    def run(self, moment: datetime):
        return (False, "Service::run not implemented")

    def getEstimatedTime(self):
        return self.estimated_dt

    def setEstimatedTime(self, dt: datetime, info_time: datetime = datetime.now().astimezone()):
        self.estimated_dt = dt
        self.schedule_history.append((dt.isoformat(), "ET", info_time.isoformat()))

    def setActualTime(self, dt: datetime, info_time: datetime = datetime.now().astimezone()):
        self.actual = dt
        self.schedule_history.append((dt.isoformat(), "AT", info_time.isoformat()))

    def started(self, dt: datetime, info_time: datetime = datetime.now()):
        self.setActualTime(dt, info_time)

    def terminated(self, dt: datetime, info_time: datetime = datetime.now().astimezone()):
        self.actual_end = dt
        self.schedule_history.append((dt.isoformat(), "TT", info_time.isoformat()))  # Terminated Time
