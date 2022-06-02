import redis

from datetime import datetime, date, time, timedelta
from typing import Optional, Literal, List

from pydantic import BaseModel, Field, validator, constr

from emitpy.constants import EMIT_RATES, REDIS_DATABASE, REDIS_LOVS
from emitpy.utils import key_path
from emitpy.parameters import REDIS_CONNECT
from emitpy.service import Mission, MissionVehicle
from emitpy.emit import Queue

from .utils import LOV_Validator, REDISLOV_Validator, ICAO24_Validator


class CreateMission(BaseModel):

    operator: str = Field(..., description="Operator code name")
    mission: str = Field(..., description="Mission identifier or name")
    mission_type: str = Field(..., description="Mission type")
    mission_vehicle_type: str = Field(..., description="Mission vehicle type")
    mission_vehicle_reg: str = Field(..., description="Mission vehicle registration")
    icao24: str = Field(..., description="Hexadecimal number of ADS-B broadcaster MAC address, exactly 6 hexadecimal digits")
    previous_position: str = Field(..., description="Position where the vehicle is coming from")
    next_position: str = Field(..., description="Position where the vehicle is going to after servicing this")
    mission_date: date = Field(..., description="Service scheduled date")
    mission_time: time = Field(time(hour=datetime.now().hour, minute=datetime.now().minute), description="Service scheduled time")
    emit_rate: int = Field(30, description="Emission rate (sent every ... seconds)")
    queue: str = Field(..., description="Name of emission broadcast queue")

    @validator('operator')
    def validate_operator(cls, operator):
        r = redis.Redis(**REDIS_CONNECT)
        return REDISLOV_Validator(redis=r,
                                  value=operator,
                                  valid_key=key_path(REDIS_DATABASE.LOVS.value,REDIS_LOVS.COMPANIES.value),
                                  invalid_message=f"Invalid point of interest code {operator}")

    @validator('mission_type')
    def validate_mission_type(cls, mission_type):
        valid_values = [e[0] for e in Mission.getCombo()]
        return LOV_Validator(value=mission_type,
                             valid_values=valid_values,
                             invalid_message=f"Mission type must be in {valid_values}")

    @validator('mission_vehicle_type')
    def validate_mission_vehicle_type(cls, mission_vehicle_type):
        valid_values = [e[0] for e in MissionVehicle.getCombo()]
        return LOV_Validator(value=mission_vehicle_type,
                             valid_values=valid_values,
                             invalid_message=f"Mission vehicle type must be in {valid_values}")

    @validator('icao24')
    def validate_icao24(cls, icao24):
        r = redis.Redis(**REDIS_CONNECT)
        return ICAO24_Validator(value=icao24)

    @validator('previous_position')
    def validate_previous_position(cls, previous_position):
        r = redis.Redis(**REDIS_CONNECT)
        return REDISLOV_Validator(redis=r,
                                  value=previous_position,
                                  valid_key=key_path(REDIS_DATABASE.LOVS.value,REDIS_LOVS.POIS.value),
                                  invalid_message=f"Invalid point of interest code {previous_position}")

    @validator('next_position')
    def validate_next_position(cls, next_position):
        r = redis.Redis(**REDIS_CONNECT)
        return REDISLOV_Validator(redis=r,
                                  value=next_position,
                                  valid_key="lovs:airport:pois",
                                  invalid_message=f"Invalid point of interest code {next_position}")

    @validator('emit_rate')
    def validate_emit_rate(cls, emit_rate):
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


class ScheduleMission(BaseModel):

    mission_id: str = Field(..., description="Mission identifier")
    sync_name: str = Field(..., description="Name of synchronization mark for new date/time schedule")
    mission_date: date = Field(..., description="Scheduled new date for the mission")
    mission_time: time = Field(time(hour=datetime.now().hour, minute=datetime.now().minute), description="Scheduled new time for the mission")
    queue: str = Field(..., description="Destination queue of mission emission")

    @validator('queue')
    def validate_queue(cls, queue):
        r = redis.Redis(**REDIS_CONNECT)
        valid_values = [q[0] for q in Queue.getCombo(r)]
        return LOV_Validator(value=queue,
                             valid_values=valid_values,
                             invalid_message=f"Invalid queue name {queue}")


class DeleteMission(BaseModel):

    mission_id: str = Field(..., description="Mission identifier")
    queue: str = Field(..., description="Destination queue")

    @validator('queue')
    def validate_queue(cls, queue):
        r = redis.Redis(**REDIS_CONNECT)
        valid_values = [q[0] for q in Queue.getCombo(r)]
        return LOV_Validator(value=queue,
                             valid_values=valid_values,
                             invalid_message=f"Invalid queue name {queue}")


