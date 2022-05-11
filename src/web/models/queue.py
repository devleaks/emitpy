from datetime import datetime, date, time, timedelta
from typing import Optional, Literal, List

from pydantic import BaseModel, Field, validator

from emitpy.constants import EMIT_RATES
from .utils import LOV_Validator


class CreateQueue(BaseModel):
    name: str = Field(..., description="Queue identifier")
    formatter: str
    queue_date: date
    queue_time: time
    speed: float
    start: bool


class ScheduleQueue(BaseModel):
    name: str = Field(..., description="Queue identifier")
    queue_date: date
    queue_time: time
    speed: float
    start: bool


