"""
EmitPy Messages are messages sent be different emitpy entities to report their activity or work.
For exemple, when a new flight is created, we create a EmitPy "new flight" message.
EmitPy Message are meant to be sent on alternate channels to prepare external resources to handle
upcoming position-related messages.
EmitPy Messages are limited to the ManagedAirport scope.
"""
import sys
import uuid
import json
import logging
from datetime import datetime, timedelta
from enum import Enum

from emitpy.utils import key_path
from emitpy.constants import MESSAGE_DATABASE, MESSAGE_COLOR, FLIGHT_TIME_FORMAT

logger = logging.getLogger("Message")


class MESSAGE_CATEGORY(Enum):
    OOOI = "oooi"
    FLIGHTINFO = "adsc"
    FLIGHTBOARD = "flightboard"
    SERVICE = "service"
    SCHEDULE = "schedule"
    MOVEMENT = "move"


class MESSAGE_STATUS(Enum):
    CREATED = "created"
    NOTIFY = "notify"  # need to be sent
    READ = "read"
    SCHEDULED = "scheduled"  # for emission
    EXPIRED = "expired"
    SENT = "sent"


class MESSAGE_ICON(Enum):
    # twitter bootstrap inspired: success,warning,error,info,primary,disabled,light,dark,default
    DEFAULT   = "default"
    INFO      = "info"
    DEPARTURE = "aircraft-departure"
    ARRIVAL   = "aircraft-arrival"
    AIRCRAFT  = "aircraft"
    GSE       = "truck"
    MARSHALL  = "taxi"


class Message:

    def __init__(self, category: str, **kwargs):

        self.ident = kwargs.get("id", f"{uuid.uuid4()}")
        # Message display
        self.source = kwargs.get("source", None)    # ~ From:
        self.subject = kwargs.get("subject", None)
        self.body = kwargs.get("body", None)

        self.link = kwargs.get("link", None)
        self.payload = kwargs.get("payload", None)

        self.icon = kwargs.get("icon", MESSAGE_ICON.DEFAULT.value)
        self.color = kwargs.get("color", MESSAGE_COLOR.DEFAULT.value)

        # Message meta-data
        self.priority = kwargs.get("priority", 3)
        self.category = category
        self.status = kwargs.get("status", MESSAGE_STATUS.CREATED.value)

        # Message timing information data and meta-data
        self.entity = kwargs.get("entity", None)             # parent entity can be emit, movement(flight, mission, service), or flight
        self.relative_sync = kwargs.get("sync", None)        # mark in parent entity

        self.relative_time = kwargs.get("relative_time", 0)  # seconds relative to above for emission

        self.scheduled_time = kwargs.get("scheduled_time", None)  # scheduled emission time
        self.absolute_time = None

    def __str__(self):
        """
        Structure that is sent to clients ("The Wire")
        """
        return json.dumps(self.getInfo())

    def getId(self):
        return self.ident

    def getKey(self, extension: str):
        return key_path(MESSAGE_DATABASE, self.getId(), extension)

    def getType(self):
        return type(self).__name__

    def getInfo(self):
        r = {
            "id": self.ident,
            "type": self.getType(),
            "category": self.category,
            "subject": self.subject,
            "body": self.body,
            "link": self.link,
            "payload": self.payload,
            "priority": self.priority,
            "icon": self.icon,
            "icon-color": self.category,
            "status": self.status,
            "relative_sync": self.relative_sync,
            "relative_time": self.relative_time
        }
        r["scheduled_time"] = None
        if self.scheduled_time is not None:
            r["scheduled_time"] = self.scheduled_time.isoformat()
        r["absolute_emission_time"] = None
        if self.absolute_time is not None:
            r["absolute_emission_time"] = self.absolute_time.isoformat()
        return r

    def schedule(self, moment):
        self.absolute_time = moment + timedelta(seconds=self.relative_time)
        logger.debug(f"{type(self).__name__}: {self.absolute_time.isoformat()} (relative={self.relative_time})")
        return self.absolute_time

    def getAbsoluteEmissionTime(self):
        if self.absolute_time is not None:
            return self.absolute_time
        else:
            return self.scheduled_time + timedelta(seconds=self.relative_time)


class ReMessage(Message):
    #
    # Message that can only be loaded, rescheduled (at will), and saved.
    # Cannot be used, or changed.
    # Used when re-scheduling a movement to reschedule messages in phase with movement.
    # (See ReEmit.)
    #
    def __init__(self, category: str, data):

        self.ident = data.get("id")
        Message.__init__(self, category=category, id=self.ident)

        self.data = data
        self.relative_sync = data.get("relative_sync")     # mark in parent entity
        self.relative_time = data.get("relative_time", 0)  # seconds relative to above for emission
        self.scheduled_time = data.get("scheduled_time")   # scheduled emission time
        self.absolute_time = None

    def getType(self):
        return self.data.get("type")

    def getInfo(self):
        r = self.data
        logger.debug(f"type is {self.data.get('type')}")

        # replace values if modified
        if self.relative_sync is not None:
            r["relative_sync"] = self.relative_sync
        if self.relative_time is not None:
            r["relative_time"] = self.relative_time
        if self.scheduled_time is not None:
            r["scheduled_time"] = self.scheduled_time

        r["absolute_emission_time"] = None
        if self.absolute_time is not None:
            r["absolute_emission_time"] = self.absolute_time.isoformat()

        return r


class Messages:
    """
    Message Trait for movements, flights, services, and missions
    """
    def __init__(self):
        self.messages = []
        self.schedule_history = []      # [(timestamp, {ETA|ETD|STA|STD}, datetime)]

    def addMessage(self, message: Message):
        self.messages.append(message)

    def getMessages(self):
        return self.messages

    def scheduleMessages(self, reftime: datetime):
        for m in self.messages:
            m.schedule(reftime)
        logger.debug(f"scheduled relative to {reftime}")

    def saveMessages(self, redis, key: str):
        for m in self.messages:
            redis.sadd(key, json.dumps(m.getInfo()))
        logger.debug(f"saved {redis.smembers(key)} messages")

    def getScheduleHistory(self, as_string: bool = False):
        if as_string:
            a = []
            for f in self.schedule_history:
                f0 = f[0] if type(f[0]) == str else f[0].isoformat()
                f2 = f[2] if type(f[2]) == str else f[2].isoformat()
                a.append((f0, f[1], f2))
            return a
        return self.schedule_history


# ########################################
#
# MESSAGE TYPES
#
class FlightboardMessage(Message):
    """
    A FlightboardMessage is a message about a scheduled arrival or departure flight from the ManagedAirport.
    """
    def __init__(self,
                 flight: "Flight",
                 **kwargs):

        self.operator = flight.operator.icao
        self.flight_number = str(flight.number)
        self.is_arrival = flight.is_arrival()
        self.airport = flight.departure.icao if self.is_arrival else flight.arrival.icao
        self.scheduled_time = flight.scheduled_dt

        title = "ARRIVAL " if self.is_arrival else "DEPARTURE "
        title = title + self.operator + self.flight_number + " "
        title = title + ("FROM " if self.is_arrival else "TO ")
        title = title + self.airport + " AT "
        title = title + self.scheduled_time.isoformat()

        Message.__init__(self,
                         category=MESSAGE_CATEGORY.FLIGHTBOARD.value,
                         entity=flight,
                         subject=title,
                         **kwargs)

    def getInfo(self):
        a = super().getInfo()
        a["scheduled-utc"] = None
        if self.scheduled_time is not None:
            a["scheduled-utc"] = self.scheduled_time.isoformat()
        return a


class EstimatedTimeMessage(Message):
    """
    A EstimatedTimeMessage is a message about a estimated time of arrival or departure flight from the ManagedAirport.
    """
    def __init__(self,
                 flight_id: str,
                 is_arrival: bool,
                 et: datetime,
                 **kwargs):

        Message.__init__(self,
                         category=MESSAGE_CATEGORY.FLIGHTINFO.value,
                         **kwargs)

        self.is_arrival = is_arrival
        a = flight_id.split("-")
        self.scheduled_time = datetime.strptime(a[1], "S" + FLIGHT_TIME_FORMAT)
        self.estimated_time = et


    def getInfo(self):
        a = super().getInfo()
        a["estimated"] = self.estimated_time.isoformat()
        return a


class MovementMessage(Message):
    """
    A MovementMessage is a message sent during a Movement (flight, service, mission).
    """
    def __init__(self,
                 subject: str,
                 move: "Movement",
                 sync: str,
                 info: dict = None,
                 **kwargs):

        Message.__init__(self,
                         subject=subject,
                         category=MESSAGE_CATEGORY.MOVEMENT.value,
                         entity=move,
                         sync=sync,
                         payload=info,
                         **kwargs)

class FlightMessage(MovementMessage):
    """
    A FilghtMessage is a message sent during a flight.
    """
    def __init__(self,
                 subject: str,
                 flight: "FlightMovement",
                 sync: str,
                 info: dict = None):

        MovementMessage.__init__(self,
                         subject=subject,
                         move=flight,
                         sync=sync,
                         info=info)

    def getInfo(self):
        a = super().getInfo()
        a["flight-event"] = self.relative_sync
        return a


class MissionMessage(MovementMessage):
    """
    A MovementMessage is a message sent during a mission.
    """
    def __init__(self,
                 subject: str,
                 mission: "MissionMovement",
                 sync: str,
                 info: dict = None,
                 **kwargs):

        MovementMessage.__init__(self,
                         subject=subject,
                         move=mission,
                         sync=sync,
                         info=info,
                         **kwargs)

    def getInfo(self):
        a = super().getInfo()
        a["mission-event"] = self.relative_sync
        return a


class ServiceMessage(MovementMessage):
    """
    A ServiceMessage is sent when a service starts or terminates.
    """
    def __init__(self,
                 subject: str,
                 service: "ServiceMovement",
                 sync: str,
                 info: dict,
                 **kwargs):

        MovementMessage.__init__(self,
                         subject=subject,
                         move=service,
                         sync=sync,
                         info=info,
                         **kwargs)

    def getInfo(self):
        a = super().getInfo()
        a["service-event"] = self.relative_sync
        return a


# class NewScheduling(Message):

#     def __init__(self,
#                  move_type: str,
#                  move_id: str,
#                  sync: str,
#                  scheduled: datetime,
#                  update_time: datetime):
#         """
#         A NewScheduling is sent when a re-scheduling of an emission is requested.
#         """
#         Message.__init__(self,
#                          category=MESSAGE_CATEGORY.SCHEDULE.value,
#                          msgsubtype=move_type,
#                          entity=move_id,
#                          subentity=sync)

# class ETDMessage(Message):

#     def __init__(self):
#         Message.__init__(self, subject="", body="")


# class MetarMessage(Message):

#     def __init__(self):
#         Message.__init__(self, subject="", body="")


