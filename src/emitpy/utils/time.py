"""
Miscellanerous general functions
"""
from datetime import datetime, timedelta
import logging
logger = logging.getLogger("Utils/Time")

from ..constants import FLIGHT_PHASE

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
    Compute the actual time for the supplied scheduled time,

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