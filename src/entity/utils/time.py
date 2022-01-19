"""
Miscellanerous general functions
"""
from datetime import datetime, timedelta
import logging
logger = logging.getLogger("Utils/Time")


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
