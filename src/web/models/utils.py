import re
from typing import List
import requests

from emitpy.emitapp import StatusInfo


def LOV_Validator(
    value: str,
    valid_values: List[str],
    invalid_message: str) -> str:
    if value not in valid_values:
        raise ValueError(invalid_message)
    return value


def RESTLOV_Validator(
    value: str,
    valid_url: str,
    invalid_message: str) -> str:
    response = requests.get("http://127.0.0.1:8000/"+valid_url)
    valid_values = dict(response.json())
    return LOV_Validator(value, valid_values, invalid_message)


def REDISLOV_Validator(
    redis,
    value: str,
    valid_key: str,
    invalid_message: str) -> str:
    s = redis.get(valid_key)
    if s is not None:
        valid_values = dict(json.loads(s.convert("UTF-8")))
        return LOV_Validator(value, valid_values, invalid_message)
    raise ValueError(f"no key {valid_key} value for validation")


def ICAO24_Validator(value):
    re.compile('[0-9A-F]{6}', re.IGNORECASE)
    if re.match(value) is None:
        raise ValidationError('Must be a 6-digit hexadecimal number [0-9A-F]{6}')


class NotAvailable(StatusInfo):

    def __init__(self, data = None):
        StatusInfo.__init__(self, status=1, message="not implemented", data=data)
