"""
EmitPy Messages are messages sent be different emitpy entities to report their activity or work.
For exemple, when a new flight is created, we create a EmitPy "new flight" message.
EmitPy Message are meant to be sent on alternate channels to prepare external resources to handle
upcoming position-related messages.
EmitPy Messages are limited to the ManagedAirport scope.
"""
import uuid
import json
from datetime import datetime, timedelta
from enum import Enum, IntEnum, Flag

from emitpy.utils import key_path
from emitpy.constants import MESSAGE_COLOR, ARRIVAL, DEPARTURE, FLIGHT_TIME_FORMAT


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
        self.ident = f"{uuid.uuid4()}"
        self.data = kwargs

        self.category = category
        self.status = kwargs.get("status", MESSAGE_STATUS.CREATED.value)

        # Related object
        self.entity = kwargs.get("entity", None)

        # Timing information
        self.move = kwargs.get("move", None)
        self.relative_sync = None  # mark in move
        self.relative_time = 0     # seconds relative to above
        self.absolute_time = None

        # Message display
        self.source = kwargs.get("source", None)    # ~ From:
        self.subject = kwargs.get("subject", None)
        self.body = kwargs.get("body", None)

        self.link = kwargs.get("link", None)
        self.payload = kwargs.get("payload", None)

        # Message meta-data
        self.priority = kwargs.get("priority", 3)

        self.icon = kwargs.get("icon", MESSAGE_ICON.DEFAULT.value)
        self.color = kwargs.get("color", MESSAGE_COLOR.DEFAULT.value)


    def __str__(self):
        """
        Structure that is sent to clients ("The Wire")
        """
        return json.dumps({
            "id": self.ident,
            "category": self.category,
            "subject": self.subject,
            "body": self.body,
            "link": self.link,
            "payload": self.payload,
            "priority": self.priority,
            "icon": self.icon,
            "icon-color": self.category,
            "status": self.status,
            "absolute_emission_time": self.absolute_time
        })

    def getId(self):
        return self.ident


    def getKey(self, extension: str):
        return key_path(MESSAGE_DATABASE, self.getId(), extension)


    def getInfo(self):
        return {
            "id": self.ident,
            "type": type(self).__name__,
            "category": self.category,
            "subject": self.subject,
            "body": self.body,
            "link": self.link,
            "payload": self.payload,
            "priority": self.priority,
            "icon": self.icon,
            "icon-color": self.category,
            "status": self.status,
            "absolute_emission_time": self.absolute_time
        }


    def setRelativeSchedule(self, entity, sync:str, relative_time: int = 0):
        """
        Sets the emission time of this message relative to sync in entity.

        :param      entity:         The entity
        :type       entity:         { type_description }
        :param      sync:           The synchronize
        :type       sync:           str
        :param      relative_time:  The relative time
        :type       relative_time:  int
        """
        pass


    def schedule(self, reftime):
        self.absolute_time = reftime + timedelta(seconds=self.relative_time)
        return self.absolute_time


    def send(self):
        pass


class Messages:
    """
    Message Trait for movements, flights, services, and missions
    """
    def __init__(self):
        self.messages = []

    def addMessage(self, message: Message):
        self.messages.append(message)

    def getMessages(self):
        return self.messages

    def saveMessages(self, redis, key: str):
        for m in self.messages:
            self.redis.sadd(key, json.dumps(m.getInfo()))
        logger.debug(f":save: saved {redis.smembers(key)} messages")


# ########################################
# MESSAGE TYPES
#
class MovementMessage(Message):
    """
    A MovementMessage is a message sent during a Movement (flight, service, mission).
    """
    def __init__(self,
                 subject: str,
                 move: "Movement",
                 sync: str,
                 info: dict = None):
        Message.__init__(self,
                         subject=subject,
                         category=MESSAGE_CATEGORY.MOVEMENT.value,
                         move=move,
                         sync=sync,
                         payload=info)

    def getInfo(self):
        a = super().getInfo()
        return a


class ServiceMessage(Message):

    def __init__(self,
                 subject: str,
                 move: "Movement",
                 sync: str,
                 info: dict,
                 service: str):
        """
        A ServiceMessage is sent when a service starts or terminates.
        """
        Message.__init__(self,
                         subject=subject,
                         category=MESSAGE_CATEGORY.SERVICE.value,
                         move=move,
                         sync=sync,
                         payload=info,
                         service=service)

        self.service_event = service

    def getInfo(self):
        a = super().getInfo()
        a["service-event"] = self.service_event
        return a


class FlightboardMessage(Message):
    """
    A FlightboardMessage is a message about a scheduled arrival or departure flight from the ManagedAirport.
    """
    def __init__(self,
                 flight_id,
                 is_arrival: bool,
                 airport):
        Message.__init__(self,
                         category=MESSAGE_CATEGORY.FLIGHTBOARD.value)

        a = flight_id.split("-")
        self.scheduled = datetime.strptime(a[1], "S" + FLIGHT_TIME_FORMAT)

    def getInfo(self):
        a = super().getInfo()
        a["scheduled-utc"] = self.scheduled
        return a


class EstimatedTimeMessage(Message):
    """
    A EstimatedTimeMessage is a message about a estimated time of arrival or departure flight from the ManagedAirport.
    """
    def __init__(self,
                 flight_id: str,
                 is_arrival: bool,
                 et: datetime):

        Message.__init__(self,
                         category=MESSAGE_CATEGORY.FLIGHTINFO.value)

        self.estimated = et


    def getInfo(self):
        a = super().getInfo()
        a["estimated"] = self.estimated.isoformat()
        return a


class NewScheduling(Message):

    def __init__(self,
                 move_type: str,
                 move_id: str,
                 sync: str,
                 scheduled: datetime,
                 update_time: datetime):
        """
        A NewScheduling is sent when a re-scheduling of an emission is requested.
        """
        Message.__init__(self,
                         category=MESSAGE_CATEGORY.SCHEDULE.value,
                         msgsubtype=move_type,
                         entity=move_id,
                         subentity=sync)

# class ETDMessage(Message):

#     def __init__(self):
#         Message.__init__(self, subject="", body="")


# class MetarMessage(Message):

#     def __init__(self):
#         Message.__init__(self, subject="", body="")


