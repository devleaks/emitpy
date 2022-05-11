import re
from typing import List
from emitpy.emitapp import StatusInfo


def LOV_Validator(
    value: str,
    valid_values: List[str],
    invalid_message: str) -> str:
    if value not in valid_values:
        raise ValueError(invalid_message)
    return value


def ICAO24_Validator(value):
    re.compile('[0-9A-F]{6}', re.IGNORECASE)
    if re.match(value) is None:
        raise ValidationError('Must be a 6-digit hexadecimal number [0-9A-F]{6}')


class NotAvailable(StatusInfo):

    def __init__(self, data = None):
        StatusInfo.__init__(self, status=1, message="not implemented", data=data)
