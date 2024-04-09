"""
This script loads a series of flights from a file.
It sorts flights by actual flight time, or scheduled time if actual flight time is not avaialble.
It then selects a number of consecutive flights and schedule them from now on.

"""

import sys

sys.path.append("..")

import csv
import os
import random
from datetime import datetime, timedelta
import logging

from emitpy.utils import Time

FORMAT = "%(levelname)1.1s%(module)22s:%(funcName)-25s%(lineno)4s| %(message)s"
logging.basicConfig(level=logging.DEBUG, format=FORMAT)
logger = logging.getLogger("emit_test")
logger_error = logging.getLogger("emit_test_errors")
handler = logging.FileHandler("emit_test_errors.log")
logger_error.addHandler(handler)

t = Time(scheduled=datetime.now())
print(t.estimated)

u = datetime.now() + timedelta(hours=2)
print(u)

t.estimated = (u, "a good reason")
print(t.scheduled, t.estimated_fmt)


print(t.get_estimated_history())


def validate_args(valid: list, **kwargs) -> list:
    """Helper function to validate keyword arguments"""
    return [f for f in kwargs if f not in valid]


def check_args(valid: list, input_list: dict):
    check = [f for f in input_list if f not in valid]
    if len(check) > 0:
        print(f"invalid kwargs: {', '.join(check)}.")


a = {"good": 1, "ugly": 2}

check_args(["good", "bad"], a)

t = validate_args(["good", "bad"], **a)
if len(t) > 0:
    print(f"invalid kwargs: {', '.join(t)}.")
