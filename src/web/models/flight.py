import redis

from typing import Optional, Literal, List
from datetime import datetime, date, time, timedelta

from pydantic import BaseModel, Field, validator, constr

from emitpy.constants import ARRIVAL, DEPARTURE, EMIT_RATES, REDIS_DATABASE, REDIS_LOVS
from emitpy.utils import key_path
from emitpy.parameters import REDIS_CONNECT
from emitpy.broadcast import Queue

from .utils import LOV_Validator, REDISLOV_Validator, ICAO24_Validator


class CreateFlight(BaseModel):

    airline: str = Field(..., description="Airline IATA identifier; must be operating at managed airport")
    flight_number: Optional[constr(max_length=5)] = Field(..., description="Flight IATA number, 1 to 5 characters maximum")
    flight_date: date = Field(..., description="Flight scheduled date in managed airport local time")
    flight_time: time = Field(time(hour=datetime.now().hour, minute=datetime.now().minute), description="Flight scheduled time in managed airport local time")
    movement: Literal[ARRIVAL, DEPARTURE] = Field(..., description="Movement, arrival or departure")
    airport: str = Field(..., description="Airport IATA identifier; must be connected with managed airport")
    ramp: str = Field(..., description="Managed airport ramp name for aircraft")
    aircraft_type: str = Field(..., description="IATA or ICAO aircraft model code (will do best effort to guess proper type)")
    aircraft_reg: str = Field(..., description="Aircraft registration (tail number)")
    call_sign: str = Field(..., description="Aircraft call sign for this flight, usually ICAO airline code and flight number")
    icao24: Optional[constr(min_length=6, max_length=6)] = Field(..., description="Hexadecimal number of ADS-B broadcaster MAC address, exactly 6 hexadecimal digits")
    runway: str = Field(..., description="Managed airport runway used for movement")
    emit_rate: int = Field(30, description="Emission rate for positions (sent every ... seconds)")
    queue: str = Field(..., description="Name of emission broadcast queue for positions; also determine emission data format")
    create_services: bool = False
    flight_actual_date: date = Field(None, description="Flight actual date in managed airport local time")
    flight_actual_time: time = Field(None, description="Flight actual time in managed airport local time")

    @validator('airline')
    def validate_airline(cls,airline):
        r = redis.Redis(**REDIS_CONNECT)
        return REDISLOV_Validator(redis=r,
                                  value=airline,
                                  valid_key=key_path(REDIS_DATABASE.LOVS.value,REDIS_LOVS.AIRLINES.value),
                                  invalid_message=f"Invalid airline code {airline}")

    @validator('airport')
    def validate_airport(cls,airport):
        r = redis.Redis(**REDIS_CONNECT)
        return REDISLOV_Validator(redis=r,
                                  value=airport,
                                  valid_key=key_path(REDIS_DATABASE.LOVS.value,REDIS_LOVS.AIRPORTS.value),
                                  invalid_message=f"Invalid airport code {airport}")

    @validator('ramp')
    def validate_ramp(cls,ramp):
        r = redis.Redis(**REDIS_CONNECT)
        return REDISLOV_Validator(redis=r,
                                  value=ramp,
                                  valid_key=key_path(REDIS_DATABASE.LOVS.value,REDIS_LOVS.RAMPS.value),
                                  invalid_message=f"Invalid ramp {ramp}")

    @validator('icao24')
    def validate_icao24(cls,icao24):
        r = redis.Redis(**REDIS_CONNECT)
        return ICAO24_Validator(value=icao24)

    @validator('aircraft_type')
    def validate_aircraft_type(cls,aircraft_type):
        r = redis.Redis(**REDIS_CONNECT)
        return REDISLOV_Validator(redis=r,
                                  value=aircraft_type,
                                  valid_key=key_path(REDIS_DATABASE.LOVS.value,REDIS_LOVS.AIRCRAFT_TYPES.value),
                                  invalid_message=f"Invalid aircraft type code {aircraft_type}")

    @validator('queue')
    def validate_queue(cls,queue):
        r = redis.Redis(**REDIS_CONNECT)
        valid_values = [q[0] for q in Queue.getCombo(r)]
        return LOV_Validator(value=queue,
                             valid_values=valid_values,
                             invalid_message=f"Invalid queue name {queue}")

    @validator('emit_rate')
    def validate_emit_rate(cls,emit_rate):
        valid_values = [int(e[0]) for e in EMIT_RATES]
        return LOV_Validator(value=emit_rate,
                             valid_values=valid_values,
                             invalid_message=f"Emit rate value must be in {valid_values} (seconds bytween pushes)")


class ScheduleFlight(BaseModel):

    flight_id: str = Field(..., description="Flight IATA identifier")
    sync_name: str = Field(..., description="Name of sychronization mark for new date time estimate")
    flight_date: date = Field(..., description="Estimated date for flight in managed airport local time")
    flight_time: time = Field(time(hour=datetime.now().hour, minute=datetime.now().minute), description="Estimated time in managed airport local time")
    queue: str = Field(..., description="Destination queue for positions")

    @validator('queue')
    def validate_queue(cls,queue):
        r = redis.Redis(**REDIS_CONNECT)
        valid_values = [q[0] for q in Queue.getCombo(r)]
        return LOV_Validator(value=queue,
                             valid_values=valid_values,
                             invalid_message=f"Invalid queue name {queue}")


class DeleteFlight(BaseModel):

    flight_id: str = Field(..., description="Flight IATA identifier")
    delete_services: bool = Field(False, description="Whether to delete associated services")
    queue: str = Field(..., description="Queue used for positions of flight")

    @validator('queue')
    def validate_queue(cls,queue):
        r = redis.Redis(**REDIS_CONNECT)
        valid_values = [q[0] for q in Queue.getCombo(r)]
        return LOV_Validator(value=queue,
                             valid_values=valid_values,
                             invalid_message=f"Invalid queue name {queue}")

