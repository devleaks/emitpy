import re
from typing import List

from emitpy.emitapp import StatusInfo
from emitpy.constants import REDIS_DB


def LOV_Validator(
    value: str,
    valid_values: List[str],
    invalid_message: str) -> str:
    if value not in valid_values:
        raise ValueError(f"key {value} not in {valid_values}")
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
    prevdb = redis.client_info()["db"]
    redis.select(REDIS_DB.REF.value)
    valid_values = redis.json().get(valid_key)
    redis.select(prevdb)
    if valid_values is not None:
        return LOV_Validator(value, valid_values.keys(), invalid_message)
    raise ValueError(f"no key {valid_key} value for validation")


def REDISKEY_Validator(
    redis,
    value: str,
    key_pattern: str,
    invalid_message: str) -> str:
    prevdb = redis.client_info()["db"]
    redis.select(REDIS_DB.APP.value)
    valid_values = redis.keys(key_pattern)
    redis.select(prevdb)
    if valid_values is not None:
        return LOV_Validator(value, [f.decode("UTF-8") for f in valid_values], invalid_message)
    raise ValueError(f"no key for '{key_pattern}' for validation")


def ICAO24_Validator(value):
    p = re.compile('[0-9A-F]{6}', re.IGNORECASE)
    if p.match(value) is None:
        raise ValueError("Must be a 6-digit hexadecimal number [0-9A-F]{6}")
    return value


class NotAvailable(StatusInfo):

    def __init__(self, data = None):
        StatusInfo.__init__(self, status=1, message="not implemented", data=data)
