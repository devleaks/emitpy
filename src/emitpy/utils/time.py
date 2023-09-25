"""
Miscellanerous general functions
"""
import logging
from datetime import datetime, timedelta

from emitpy.constants import FLIGHT_PHASE

logger = logging.getLogger("Utils/Time")


class EstimatedTime:
    def __init__(
        self,
        estimated: datetime,
        timestamp: datetime,
        reason: str,
        estimator: str = None,
    ):
        self.estimated = estimated
        self.timestamp = timestamp
        self.reason = reason
        self.estimator = estimator

    def getInfo(self):
        return {
            "estimated": self.estimated,
            "timestamp": self.timestamp,
            "reason": self.reason,
            "estimator": self.estimator,
        }


def roundTime(dt: datetime, roundTo: int = 300, seconds: int = 0, minutes: int = 0):
    """Round a datetime object to any time lapse in seconds
    dt : datetime.datetime object, default now.
    roundTo : Closest number of seconds to round to, default 5 minutes (300 seconds).
    Author: Thierry Husson 2012 - Use it as you want but don't blame me.
    """
    rt = roundTo + seconds + (minutes * 60)
    if dt == None:
        dt = datetime.now()
    seconds = (dt.replace(tzinfo=None) - dt.min).seconds
    rounding = (seconds + rt / 2) // rt * rt
    return dt + timedelta(0, rounding - seconds, -dt.microsecond)


def actual_time(scheduled_time: str, is_arrival: bool, delay: int, block: bool = True):
    """
    Compute the actual time for the supplied scheduled time, and delay in minutes.
    Returns actual take-off or touch-down time, or off-block and on-block time if block is True.

    :param      scheduled_time:  The scheduled time
    :type       scheduled_time:  { type_description }
    :param      arrival:         The arrival
    :type       arrival:         { type_description }
    :param      delay:           The delay
    :type       delay:           { type_description }
    """
    if block:
        if is_arrival:
            sync = FLIGHT_PHASE.ONBLOCK.value
        else:
            sync = FLIGHT_PHASE.OFFBLOCK.value
    else:
        if is_arrival:
            sync = FLIGHT_PHASE.TOUCH_DOWN.value
        else:
            sync = FLIGHT_PHASE.TAKE_OFF.value
    dt = datetime.now() + timedelta(minutes=delay)

    return f".schedule('{dt.isoformat()}', '{sync}')"


# import re
# from json import JSONEncoder, JSONDecoder

# subclass JSONEncoder
# class DateTimeEncoder(JSONEncoder):
#         #Override the default method
#         def default(self, obj):
#             if isinstance(obj, (datetime.date, datetime.datetime)):
#                 return obj.isoformat()

# class DateTimeDecoder(JSONDecoder):
#         iso8601 = r"/^([\+-]?\d{4}(?!\d{2}\b))((-?)((0[1-9]|1[0-2])(\3([12]\d|0[1-9]|3[01]))?|W([0-4]\d|5[0-2])(-?[1-7])?|(00[1-9]|0[1-9]\d|[12]\d{2}|3([0-5]\d|6[1-6])))([T\s]((([01]\d|2[0-3])((:?)[0-5]\d)?|24\:?00)([\.,]\d+(?!:))?)?(\17[0-5]\d([\.,]\d+)?)?([zZ]|([\+-])([01]\d|2[0-3]):?([0-5]\d)?)?)?)?$/"
#         def default(self, obj):
#             if isinstance(obj, str) and re.match(iso8601, obj):
#                 return datetime.fromisoformat(obj)
