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


class MESSAGE_STATUS(Enum):
    CREATED = "created"
    READ = "read"
    SCHEDULED = "scheduled"  # for emission
    EXPIRED = "expired"
    SENT = "sent"


class MESSAGE_CATEGORY(Enum):
    # twitter bootstrap inspired: success,warning,error,info,primary,disabled,light,dark,default
    DEFAULT = "default"


class Message:

    def __init__(self, subject: str, body: str):
        self.ident = uuid.uuid4()
        self.subject = subject
        self.body = body
        self.link = None
        self.payload = None

        self.source = "emitpy"

        self.priority = 3
        self.category = MESSAGE_CATEGORY.DEFAULT.value
        self.icon = "info"
        self.color = "#8888FF"
        self.status = MESSAGE_STATUS.CREATED.value

        self.relative_reference = "start"
        self.relative_time = 0  # seconds

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
            "status": self.status
        })


    def schedule(self, reftime):
        self.absolute_time = reftime + timedelta(seconds=self.relative_time)
        return self.absolute_time


class MovementMessage(Message):
    """
    A MovementMessage is a message about a scheduled arrival or departure flight from the ManagedAirport.
    """
    def __init__(self):
        Message.__init__(self, subject="", body="")


class ETAMessage(Message):

    def __init__(self):
        Message.__init__(self, subject="", body="")


class ETDMessage(Message):

    def __init__(self):
        Message.__init__(self, subject="", body="")


class GSEMessage(Message):

    def __init__(self):
        Message.__init__(self, subject="", body="")


class MetarMessage(Message):

    def __init__(self):
        Message.__init__(self, subject="", body="")



