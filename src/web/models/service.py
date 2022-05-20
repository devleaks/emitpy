import redis

from datetime import datetime, date, time, timedelta
from typing import Optional, Literal, List

from pydantic import BaseModel, Field, validator, constr

from emitpy.constants import EMIT_RATES
from emitpy.parameters import REDIS_CONNECT
from emitpy.service import Service, ServiceVehicle
from emitpy.emit import Queue

from .utils import LOV_Validator, REDISLOV_Validator, ICAO24_Validator


class CreateService(BaseModel):

    ramp: str = Field(..., description="Managed airport ramp name")
    aircraft_type: str = Field(..., description="IATA or ICAO aircraft model code")
    handler: str = Field(..., description="Operator code name")
    service_type: str = Field(..., description="Type of service")
    quantity: float = Field(..., description="Quantity of service, used to determine service duration")
    service_vehicle_model: str = Field(..., description="Model of service vehicle used")
    service_vehicle_reg: str = Field(..., description="Registration of service vehicle used")
    icao24: Optional[constr(min_length=6, max_length=6)] = Field(..., description="Hexadecimal number of ADS-B broadcaster MAC address, exactly 6 hexadecimal digits")
    previous_position: str = Field(..., description="Position where the vehicle is coming from")
    next_position: str = Field(..., description="Position where the vehicle is going to after servicing this")
    service_date: date = Field(..., description="Service scheduled date")
    service_time: time = Field(time(hour=datetime.now().hour, minute=datetime.now().minute), description="Service scheduled time")
    emit_rate: int = Field(30, description="Emission rate (sent every ... seconds)")
    queue: str = Field(..., description="Name of emission broadcast queue")

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
                                  valid_key="lovs:aircrafts",
                                  invalid_message=f"Invalid aircraft type code {aircraft_type}")

    @validator('ramp')
    def validate_ramp(cls,ramp):
        r = redis.Redis(**REDIS_CONNECT)
        return REDISLOV_Validator(redis=r,
                                  value=ramp,
                                  valid_key="lovs:airport:ramps",
                                  invalid_message=f"Invalid ramp {ramp}")

    @validator('service_vehicle_model')
    def validate_service_vehicle_type(cls,service_vehicle_model):
        valid_values = [e[0] for e in ServiceVehicle.getCombo()]
        return LOV_Validator(value=service_vehicle_model,
                             valid_values=valid_values,
                             invalid_message=f"Service vehicle model must be in {valid_values}")

    @validator('icao24')
    def validate_icao24(cls,icao24):
        r = redis.Redis(**REDIS_CONNECT)
        return ICAO24_Validator(value=icao24)

    @validator('previous_position')
    def validate_previous_position(cls,previous_position):
        r = redis.Redis(**REDIS_CONNECT)
        return REDISLOV_Validator(redis=r,
                                  value=previous_position,
                                  valid_key="lovs:airport:pois",
                                  invalid_message=f"Invalid point of interest code {previous_position}")

    @validator('next_position')
    def validate_next_position(cls,next_position):
        r = redis.Redis(**REDIS_CONNECT)
        return REDISLOV_Validator(redis=r,
                                  value=next_position,
                                  valid_key="lovs:airport:pois",
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
    service_date: date = Field(..., description="Scheduled new date for the service")
    service_time: time = Field(..., description="Scheduled new time for the service")
    queue: str = Field(..., description="Name of emission broadcast queue")

    @validator('queue')
    def validate_queue(cls,queue):
        r = redis.Redis(**REDIS_CONNECT)
        valid_values = [q[0] for q in Queue.getCombo(r)]
        return LOV_Validator(value=queue,
                             valid_values=valid_values,
                             invalid_message=f"Invalid queue name {queue}")


class DeleteService(BaseModel):

    service_id: str = Field(..., description="Mission identifier")
    queue: str = Field(..., description="Name of queue where emission is located")

    @validator('queue')
    def validate_queue(cls,queue):
        r = redis.Redis(**REDIS_CONNECT)
        valid_values = [q[0] for q in Queue.getCombo(r)]
        return LOV_Validator(value=queue,
                             valid_values=valid_values,
                             invalid_message=f"Invalid queue name {queue}")


class CreateFlightServices(BaseModel):

    flight_id: str = Field(..., description="Flight IATA identifier")
    emit_rate: int = 30
    queue: str = Field(..., description="Name of emission broadcast queue")

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
    flight_date: datetime = Field(..., description="Scheduled date time for flight (arrival or departure), services will be scheduled according to PTS")


