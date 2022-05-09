from typing import List
from emitpy.emitapp import StatusInfo

def LOV_Validator(
    value: str,
    valid_values: List[str],
    invalid_message: str) -> str:
    if value not in valid_values:
        raise ValueError(invalid_message)
    return value


class NotAvailable(StatusInfo):

    def __init__(self, data = None):
        StatusInfo.__init__(self, status=1, message="not implemented", data=data)
