import redis

from datetime import datetime, date, time, timedelta
from typing import Optional, Literal, List

from pydantic import BaseModel, Field, validator

from emitpy.constants import EMIT_RATES
from emitpy.parameters import REDIS_CONNECT
from emitpy.emit import Format, Queue

from .utils import LOV_Validator


class CreateQueue(BaseModel):

    name: str = Field(..., description="Queue identifier")
    formatter: str = Field(..., description="Name of internal data formatter")
    queue_date: Optional[date] = Field(..., description="Start date of queue, use current time if not supplied")
    queue_time: Optional[time] = Field(time(hour=datetime.now().hour, minute=datetime.now().minute), description="Start time of queue, use current time if not supplied")
    speed: float = Field(1.0, description="Speed of replay of queue")
    start: bool = Field(True, description="Queue is enabled or disabled")

    @validator('formatter')
    def validate_formatter(cls,formatter):
        r = redis.Redis(**REDIS_CONNECT)
        valid_values = [q[0] for q in Format.getCombo()]
        return LOV_Validator(value=formatter,
                             valid_values=valid_values,
                             invalid_message=f"Invalid formatter code {formatter}")


class ScheduleQueue(BaseModel):

    name: str = Field(..., description="Queue identifier")
    queue_date: Optional[date] = Field(..., description="Start date of queue, use current time if not supplied")
    queue_time: Optional[time] = Field(time(hour=datetime.now().hour, minute=datetime.now().minute), description="Start time of queue, use current time if not supplied")
    speed: float = Field(1.0, description="Speed of replay of queue")
    start: bool = Field(True, description="Queue is enabled or disabled")

    @validator('name')
    def validate_queue(cls,name):
        r = redis.Redis(**REDIS_CONNECT)
        valid_values = [q[0] for q in Queue.getCombo(r)]
        return LOV_Validator(value=name,
                             valid_values=valid_values,
                             invalid_message=f"Invalid queue name {name}")


class PiasEmit(BaseModel):

    emit_id: str = Field(..., description="Emitpy enqueued data identifier")
    queue: str = Field(..., description="Destination queue")

    @validator('queue')
    def validate_queue(cls,queue):
        r = redis.Redis(**REDIS_CONNECT)
        valid_values = [q[0] for q in Queue.getCombo(r)]
        print(">>>", valid_values)
        return LOV_Validator(value=queue,
                             valid_values=valid_values,
                             invalid_message=f"Invalid queue name {queue}")
