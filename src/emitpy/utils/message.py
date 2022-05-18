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

from emitpy.constants import MESSAGE_COLOR, ARRIVAL, DEPARTURE


class MESSAGE_TYPE(Enum):
    OOOI = "oooi"
    FLIGHTINFO = "adsc"
    FLIGHTBOARD = "flightboard"
    SERVICE = "service"
    SCHEDULE = "schedule"


class MESSAGE_STATUS(Enum):
    CREATED = "created"
    READ = "read"
    SCHEDULED = "scheduled"  # for emission
    EXPIRED = "expired"
    SENT = "sent"


class MESSAGE_CATEGORY(Enum):
    # twitter bootstrap inspired: success,warning,error,info,primary,disabled,light,dark,default
    DEFAULT = "default"


class MESSAGE_ICON(Enum):
    # twitter bootstrap inspired: success,warning,error,info,primary,disabled,light,dark,default
    DEFAULT = "default"


class Message:

    def __init__(self, msgtype: str, msgsubtype: str, entity = None, subentity = None, **kwargs):
        self.ident = f"{uuid.uuid4()}"
        self.msgtype = msgtype
        self.msgsubtype = msgsubtype
        self.data = kwargs

        # Wdb
        self.entity = entity
        self.subentity = subentity

        # Message display
        self.source = None    # ~ From:
        self.subject = None
        self.body = None

        self.link = None
        self.payload = kwargs

        # Message meta-data
        self.priority = 3
        self.category = MESSAGE_CATEGORY.DEFAULT.value
        self.icon = MESSAGE_ICON.DEFAULT.value
        self.color = MESSAGE_COLOR.DEFAULT.value
        self.status = MESSAGE_STATUS.CREATED.value
        # Timing information
        self.relative_sync = None  # mark in move
        self.relative_time = 0     # seconds relative to above

        self.absolute_time = None


    def __str__(self):
        """
        Structure that is sent to clients ("The Wire")
        """
        return json.dumps({
            "id": self.ident,
            "subject": self.subject,
            "body": self.body,
            "link": self.link,
            "payload": self.payload,
            "priority": self.priority,
            "icon": self.icon,
            "icon-color": self.category,
            "status": self.status,
            "emission_time": self.absolute_time
        })

    def getId(self):
        return self.ident

    def getKey(self, extension: str):
        return key_path(MESSAGE_DATABASE, self.getId(), extension)

    def getInfo(self):
        return {
            "ident": self.ident,
            "type": self.msgtype,
            "subtype": self.msgsubtype,
            "entity": self.entity is not None,
            "subentity": self.subentity is not None
        }

    def schedule(self, reftime):
        self.absolute_time = reftime + timedelta(seconds=self.relative_time)
        return self.absolute_time


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


class MovementMessage(Message):
    """
    A MovementMessage is a message about a scheduled arrival or departure flight from the ManagedAirport.
    """
    def __init__(self, msgtype: str, msgsubtype: str, move: "Movement" = None, feature: "Feature" = None):
        Message.__init__(self, msgtype=msgtype, msgsubtype=msgsubtype, entity=move, subentity=feature)

    def getInfo(self):
        a = {
            "ident": self.ident,
            "type": self.msgtype,
            "subtype": self.msgsubtype
        }
        if self.entity is not None:  # we know it is a Movement
            a["entity"] = self.entity.getInfo()
        if self.subentity is not None:  # we know it is a Feature
            a["subentity"] = self.subentity["properties"]
        return a


class FlightboardMessage(Message):

    def __init__(self, flight_id, is_arrival: bool, airport):
        Message.__init__(self, msgtype=MESSAGE_TYPE.FLIGHTBOARD.value,
                               msgsubtype=ARRIVAL if is_arrival else DEPARTURE,
                               entity=flight_id,
                               subentity=airport)

class EstimatedTimeMessage(Message):

    def __init__(self, flight_id: str, is_arrival: bool, et: datetime):
        Message.__init__(self, msgtype=MESSAGE_TYPE.FLIGHTINFO.value,
                               msgsubtype=ARRIVAL if is_arrival else DEPARTURE,
                               entity=flight_id,
                               subentity=et)

class NewScheduling(Message):

    def __init__(self, move_type: str, move_id: str, sync: str, scheduled: datetime, update_time: datetime):
        Message.__init__(self, msgtype=MESSAGE_TYPE.SCHEDULE.value,
                               msgsubtype=move_type,
                               entity=move_id,
                               subentity=sync)

# class ETDMessage(Message):

#     def __init__(self):
#         Message.__init__(self, subject="", body="")


# class GSEMessage(Message):

#     def __init__(self):
#         Message.__init__(self, subject="", body="")


# class MetarMessage(Message):

#     def __init__(self):
#         Message.__init__(self, subject="", body="")


