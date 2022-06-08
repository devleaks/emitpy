"""
Miscellanerous general functions
"""
from datetime import datetime, timedelta
import logging
logger = logging.getLogger("Utils/Time")

from emitpy.constants import FLIGHT_PHASE

def roundTime(dt: datetime, roundTo: int = 300):
    """Round a datetime object to any time lapse in seconds
    dt : datetime.datetime object, default now.
    roundTo : Closest number of seconds to round to, default 5 minutes.
    Author: Thierry Husson 2012 - Use it as you want but don't blame me.
    """
    if dt == None:
        dt = datetime.now()
    seconds = (dt.replace(tzinfo=None) - dt.min).seconds
    rounding = (seconds + roundTo / 2) // roundTo * roundTo
    return dt + timedelta(0, rounding-seconds, -dt.microsecond)

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
# from datetime import datetime

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
