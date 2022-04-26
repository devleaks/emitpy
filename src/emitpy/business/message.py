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
from ..constants import MESSAGE_COLOR

class MESSAGE_TYPE(Enum):
    OOOI = "oooi"
    FLIGHTBOARD = "flightboard"
    SERVICE = "service"


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

    def __init__(self, msgtype: str, msgsubtype: str, move: "Movement" = None, feature: "Feature" = None):
        self.ident = f"{uuid.uuid4()}"
        self.msgtype = msgtype
        self.msgsubtype = msgsubtype

        self.move = move
        self.feature = feature

        # Message display
        self.source = None    # ~ From:
        self.subject = None
        self.body = None

        self.link = None
        self.payload = None

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

    def getInfo(self):
        a = {
            "ident": self.ident,
            "type": self.msgtype,
            "subtype": self.msgsubtype
        }
        if self.move is not None:
            a["move"] = self.move.getInfo()
        if self.feature is not None:
            a["feature"] = self.feature["properties"]
        return a

    def schedule(self, reftime):
        self.absolute_time = reftime + timedelta(seconds=self.relative_time)
        return self.absolute_time


class Messages:
    """
    Message Trait for movements, flights, services, and missions
    """
    def __init__(self, entity):
        self.entity = entity
        self.messages = []

    def addMessage(self, message: Message):
        self.messages.append(message)

    def getMessages(self):
        return self.messages

    def saveMessages(self, redis, key: str):
        for m in self.messages:
            self.redis.sadd(key, json.dumps(m.getInfo()))
        logger.debug(f":saveDB: saved {redis.smembers(key)} messages")


# class MovementMessage(Message):
#     """
#     A MovementMessage is a message about a scheduled arrival or departure flight from the ManagedAirport.
#     """
#     def __init__(self):
#         Message.__init__(self, subject="", body="")


# class ETAMessage(Message):

#     def __init__(self):
#         Message.__init__(self, subject="", body="")


# class ETDMessage(Message):

#     def __init__(self):
#         Message.__init__(self, subject="", body="")


# class GSEMessage(Message):

#     def __init__(self):
#         Message.__init__(self, subject="", body="")


# class MetarMessage(Message):

#     def __init__(self):
#         Message.__init__(self, subject="", body="")



