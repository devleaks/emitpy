import redis

from datetime import datetime, date, time, timedelta
from typing import Optional, Literal, List

from pydantic import BaseModel, Field, validator, constr

from emitpy.constants import EMIT_RATES, REDIS_DATABASE, REDIS_LOVS
from emitpy.utils import key_path
from emitpy.parameters import REDIS_CONNECT
from emitpy.service import Service, Equipment
from emitpy.broadcast import Queue

from .utils import LOV_Validator, REDISLOV_Validator, ICAO24_Validator


class CreateService(BaseModel):

    handler: str = Field(..., description="Service handler or operator code name")
    ramp: str = Field(..., description="Managed airport ramp name")
    aircraft_type: str = Field(..., description="IATA or ICAO aircraft model code")
    service_type: str = Field(..., description="Type of service")
    quantity: float = Field(..., description="Quantity of service (float number, meaning varies with service), used to determine service duration")
    equipment_model: str = Field(..., description="Model of equipment used")
    equipment_reg: str = Field(..., description="Registration of equipment used")
    icao24: Optional[constr(min_length=6, max_length=6)] = Field(..., description="Hexadecimal number of ADS-B broadcaster MAC address, exactly 6 hexadecimal digits")
    previous_position: str = Field(..., description="Position where the equipment is coming from before this service")
    next_position: str = Field(..., description="Position where the equipment is going to after this service")
    service_date: date = Field(..., description="Service scheduled date in managed airport local time")
    service_time: time = Field(time(hour=datetime.now().hour, minute=datetime.now().minute), description="Service scheduled time in managed airport local time")
    emit_rate: int = Field(30, description="Emission rate for position of equipment (sent every ... seconds)")
    queue: str = Field(..., description="Name of emission broadcast queue for positions of equipment")

    @validator('handler')
    def validate_handler(cls,handler):
        r = redis.Redis(**REDIS_CONNECT)
        return REDISLOV_Validator(redis=r,
                                  value=handler,
                                  valid_key=key_path(REDIS_DATABASE.LOVS.value,REDIS_LOVS.COMPANIES.value),
                                  invalid_message=f"Invalid company code {handler}")

    @validator('service_type')
    def validate_service_type(cls,service_type):
        valid_values = [e[0] for e in Service.getCombo()]
        return LOV_Validator(value=service_type,
                             valid_values=valid_values,
                             invalid_message=f"Invalid service type, should be in {valid_values}")

    @validator('aircraft_type')
    def validate_aircraft_type(cls,aircraft_type):
        r = redis.Redis(**REDIS_CONNECT)
        return REDISLOV_Validator(redis=r,
                                  value=aircraft_type,
                                  valid_key=key_path(REDIS_DATABASE.LOVS.value,REDIS_LOVS.AIRCRAFT_TYPES.value),
                                  invalid_message=f"Invalid aircraft type code {aircraft_type}")

    @validator('ramp')
    def validate_ramp(cls,ramp):
        r = redis.Redis(**REDIS_CONNECT)
        return REDISLOV_Validator(redis=r,
                                  value=ramp,
                                  valid_key=key_path(REDIS_DATABASE.LOVS.value,REDIS_LOVS.RAMPS.value),
                                  invalid_message=f"Invalid ramp {ramp}")

    @validator('equipment_model')
    def validate_equipment_type(cls,equipment_model):
        valid_values = [e[0] for e in Equipment.getCombo()]
        return LOV_Validator(value=equipment_model,
                             valid_values=valid_values,
                             invalid_message=f"Equipment model must be in {valid_values}")

    @validator('icao24')
    def validate_icao24(cls,icao24):
        r = redis.Redis(**REDIS_CONNECT)
        return ICAO24_Validator(value=icao24)

    @validator('previous_position')
    def validate_previous_position(cls,previous_position):
        r = redis.Redis(**REDIS_CONNECT)
        return REDISLOV_Validator(redis=r,
                                  value=previous_position,
                                  valid_key=key_path(REDIS_DATABASE.LOVS.value,REDIS_LOVS.POIS.value),
                                  invalid_message=f"Invalid point of interest code {previous_position}")

    @validator('next_position')
    def validate_next_position(cls,next_position):
        r = redis.Redis(**REDIS_CONNECT)
        return REDISLOV_Validator(redis=r,
                                  value=next_position,
                                  valid_key=key_path(REDIS_DATABASE.LOVS.value,REDIS_LOVS.POIS.value),
                                  invalid_message=f"Invalid point of interest code {next_position}")

    @validator('emit_rate')
    def validate_emit_rate(cls,emit_rate):
        valid_values = [int(e[0]) for e in EMIT_RATES]
        return LOV_Validator(value=emit_rate,
                             valid_values=valid_values,
                             invalid_message=f"Emit rate value must be in {valid_values} (seconds)")

    @validator('queue')
    def validate_queue(cls, queue):
        r = redis.Redis(**REDIS_CONNECT)
        valid_values = [q[0] for q in Queue.getCombo(r)]
        return LOV_Validator(value=queue,
                             valid_values=valid_values,
                             invalid_message=f"Invalid queue name {queue}")


class ScheduleService(BaseModel):

    service_id: str = Field(..., description="Service identifier")
    sync_name: str = Field(..., description="Name of synchronization mark for new date/time schedule")
    service_date: date = Field(..., description="Scheduled new date for the service in managed airport local time")
    service_time: time = Field(..., description="Scheduled new time for the service in managed airport local time")
    queue: str = Field(..., description="Name of emission broadcast queue for positions")

    @validator('queue')
    def validate_queue(cls,queue):
        r = redis.Redis(**REDIS_CONNECT)
        valid_values = [q[0] for q in Queue.getCombo(r)]
        return LOV_Validator(value=queue,
                             valid_values=valid_values,
                             invalid_message=f"Invalid queue name {queue}")


class DeleteService(BaseModel):

    service_id: str = Field(..., description="Mission identifier")
    queue: str = Field(..., description="Name of queue where positions are emitted")

    @validator('queue')
    def validate_queue(cls,queue):
        r = redis.Redis(**REDIS_CONNECT)
        valid_values = [q[0] for q in Queue.getCombo(r)]
        return LOV_Validator(value=queue,
                             valid_values=valid_values,
                             invalid_message=f"Invalid queue name {queue}")


class CreateFlightServices(BaseModel):

    flight_id: str = Field(..., description="Flight IATA identifier")
    handler: str = Field(..., description="Operator code name")
    emit_rate: int = Field(30, description="Position emission rate for equipment")
    queue: str = Field(..., description="Name of emission broadcast queue for positions of equipment")

    @validator('handler')
    def validate_handler(cls,handler):
        r = redis.Redis(**REDIS_CONNECT)
        return REDISLOV_Validator(redis=r,
                                  value=handler,
                                  valid_key=key_path(REDIS_DATABASE.LOVS.value,REDIS_LOVS.COMPANIES.value),
                                  invalid_message=f"Invalid company code {handler}")

    @validator('emit_rate')
    def validate_emit_rate(cls,emit_rate):
        valid_values = [int(e[0]) for e in EMIT_RATES]
        return LOV_Validator(value=emit_rate,
                             valid_values=valid_values,
                             invalid_message=f"Emit rate value must be in {valid_values} (seconds)")

    @validator('queue')
    def validate_queue(cls,queue):
        r = redis.Redis(**REDIS_CONNECT)
        valid_values = [q[0] for q in Queue.getCombo(r)]
        return LOV_Validator(value=queue,
                             valid_values=valid_values,
                             invalid_message=f"Invalid queue name {queue}")


class ScheduleFlightServices(BaseModel):
    flight_id: str = Field(..., description="Flight IATA identifier")
    sync_name: str = Field(..., description="Name of sychronization mark for estimated date time")
    flight_date: date = Field(..., description="Estimatated flight date in managed airport local time in managed airport local time")
    flight_time: time = Field(time(hour=datetime.now().hour, minute=datetime.now().minute), description="Estimatated flight time in managed airport local time")
    # flight_date: datetime = Field(..., description="Scheduled date time for flight (arrival or departure), services will be scheduled according to PTS")
    queue: str = Field(..., description="Name of emission broadcast queue for positions of aicraft and equipment")

