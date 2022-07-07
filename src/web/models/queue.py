import redis

from datetime import datetime, date, time, timedelta
from typing import Optional, Literal, List

from pydantic import BaseModel, Field, validator

from emitpy.constants import EMIT_RATES, REDIS_TYPE
from emitpy.utils import key_path
from emitpy.parameters import REDIS_CONNECT
from emitpy.broadcast import Format, Queue

from .utils import LOV_Validator, REDISKEY_Validator


class CreateQueue(BaseModel):

    name: str = Field(..., description="Queue name")
    formatter: str = Field(..., description="Name of data formatter")
    queue_date: Optional[date] = Field(..., description="Start date of queue, uses current time if not supplied")
    queue_time: Optional[time] = Field(time(hour=datetime.now().hour, minute=datetime.now().minute), description="Start time of queue, uses current time if not supplied")
    speed: float = Field(1.0, description="Speed of replay of queue")
    start: bool = Field(True, description="Queue is enabled or disabled (started or not)")

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
    start: bool = Field(True, description="Queue is enabled or disabled (started or not)")

    @validator('name')
    def validate_queue(cls,name):
        r = redis.Redis(**REDIS_CONNECT)
        valid_values = [q[0] for q in Queue.getCombo(r)]
        return LOV_Validator(value=name,
                             valid_values=valid_values,
                             invalid_message=f"Invalid queue name {name}")


class PiasEnqueue(BaseModel):

    enqueue_id: str = Field(..., description="Emitpy enqueued data identifier")
    queue: str = Field(..., description="Destination queue")

    @validator('queue')
    def validate_queue(cls,queue):
        r = redis.Redis(**REDIS_CONNECT)
        valid_values = [q[0] for q in Queue.getCombo(r)]
        return LOV_Validator(value=queue,
                             valid_values=valid_values,
                             invalid_message=f"Invalid queue name {queue}")

    @validator('enqueue_id')
    def validate_enqueue(cls, enqueue_id):
        r = redis.Redis(**REDIS_CONNECT)
        return REDISKEY_Validator(redis=r,
                                  value=enqueue_id,
                                  key_pattern=key_path("*", REDIS_TYPE.QUEUE.value),
                                  invalid_message=f"no enqueue {enqueue_id}")

class EmitDifferent(BaseModel):

    emit_id: str = Field(..., description="Emitpy emit data identifier")
    sync_name: str = Field(..., description="Name of sychronization mark for new date time")
    sync_date: date = Field(..., description="Esimated new date for flight")
    sync_time: time = Field(time(hour=datetime.now().hour, minute=datetime.now().minute), description="Esimated time in managed airport local time")
    new_emit_rate: int = Field(30, description="Emission rate for emission of positions (sent every ... seconds)")
    queue: str = Field(..., description="Destination queue for positions")

    @validator('queue')
    def validate_queue(cls,queue):
        r = redis.Redis(**REDIS_CONNECT)
        valid_values = [q[0] for q in Queue.getCombo(r)]
        return LOV_Validator(value=queue,
                             valid_values=valid_values,
                             invalid_message=f"Invalid queue name {queue}")

    @validator('new_emit_rate')
    def validate_emit_rate(cls,new_emit_rate):
        valid_values = [int(e[0]) for e in EMIT_RATES]
        return LOV_Validator(value=new_emit_rate,
                             valid_values=valid_values,
                             invalid_message=f"Emit rate value must be in {valid_values} (seconds bytween pushes)")

    @validator('emit_id')
    def validate_enqueue(cls, emit_id):
        r = redis.Redis(**REDIS_CONNECT)
        return REDISKEY_Validator(redis=r,
                                  value=emit_id,
                                  key_pattern=key_path("*", REDIS_TYPE.EMIT.value),
                                  invalid_message=f"no enqueue {emit_id}")

