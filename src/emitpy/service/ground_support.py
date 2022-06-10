"""
A Service  is a maintenance operation performed on an aircraft during a turn-around.

"""
import sys
import logging
from datetime import datetime
from typing import Union
from types import NoneType

from emitpy.constants import SERVICE, ID_SEP
from emitpy.utils import key_path
from .servicevehicle import ServiceVehicle

logger = logging.getLogger("GroundSupport")


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
        self.pts_scheduled   = None       # absolute time for above
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
            "schedule": self.pts_reltime,
            "duration": self.pts_duration,
            "name": self.name
        }

    def getScheduleHistory(self, as_string: bool = False):
        if as_string:
            a = []
            for f in self.schedule_history:
                f0 = f[0] if type(f[0]) == str else f[0].isoformat()
                f2 = f[2] if type(f[2]) == str else f[2].isoformat()
                a.append((f0, f[1], f2))
            return a
        return self.schedule_history

    def setPTS(self, relstartime: int, duration: int):
        self.pts_reltime   = relstartime
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

    def setEstimatedTime(self, dt: datetime, info_time: datetime = datetime.now().astimezone()):
        self.estimated = dt
        self.schedule_history.append((dt.isoformat(), "ET", info_time.isoformat()))

    def setActualTime(self, dt: datetime, info_time: datetime = datetime.now().astimezone()):
        self.actual = dt
        self.schedule_history.append((dt.isoformat(), "AT", info_time.isoformat()))

    def started(self, dt: datetime, info_time: datetime = datetime.now()):
        self.setActualTime(dt, info_time)

    def terminated(self, dt: datetime, info_time: datetime = datetime.now().astimezone()):
        self.actual_end = dt
        self.schedule_history.append((dt.isoformat(), "TT", info_time.isoformat()))  # Terminated Time
