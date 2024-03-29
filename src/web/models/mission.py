import redis

from datetime import datetime, date, time, timedelta
from typing import Optional, Literal, List

from pydantic import BaseModel, Field, validator

from emitpy.constants import EMIT_RATES, REDIS_DATABASE, REDIS_LOVS
from emitpy.utils import key_path
from emitpy.parameters import REDIS_CONNECT
from emitpy.service import Mission, MissionVehicle
from emitpy.broadcast import Queue

from .utils import LOV_Validator, REDISLOV_Validator, ICAO24_Validator


class CreateMission(BaseModel):

    operator: str = Field(..., description="Mission operator code name")
    mission: str = Field(..., description="Mission identifier or name")
    mission_type: str = Field(..., description="Mission type")
    mission_vehicle_model: str = Field(..., description="Mission vehicle model")
    mission_vehicle_reg: str = Field(..., description="Mission vehicle registration")
    icao24: str = Field(..., description="Hexadecimal number of ADS-B broadcaster MAC address, exactly 6 hexadecimal digits")
    previous_position: str = Field(..., description="Position where the vehicle is coming from")
    next_position: str = Field(..., description="Position where the vehicle is going to after this mission is terminated")
    checkpoints: List[str] = Field([], description="Positions to check during the mission")
    mission_date: date = Field(..., description="Service scheduled date in managed airport local time")
    mission_time: time = Field(time(hour=datetime.now().hour, minute=datetime.now().minute), description="Service scheduled time in managed airport local time")
    emit_rate: int = Field(30, description="Emission rate for positions of mission vehicle (sent every ... seconds)")
    queue: str = Field(..., description="Name of emission broadcast queue for positions")

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

    @validator('mission_vehicle_model')
    def validate_mission_vehicle_model(cls, mission_vehicle_model):
        valid_values = [e[0] for e in MissionVehicle.getCombo()]
        return LOV_Validator(value=mission_vehicle_model,
                             valid_values=valid_values,
                             invalid_message=f"Mission vehicle model must be in {valid_values}")

    @validator('icao24')
    def validate_icao24(cls, icao24):
        r = redis.Redis(**REDIS_CONNECT)
        return ICAO24_Validator(value=icao24)

    @validator('checkpoints')
    def validate_checkpoints(cls, checkpoints):
        r = redis.Redis(**REDIS_CONNECT)
        return [REDISLOV_Validator(redis=r,
                                   value=c,
                                   valid_key=key_path(REDIS_DATABASE.LOVS.value,REDIS_LOVS.POIS.value),
                                   invalid_message=f"Invalid checkpoint code {c}") for c in checkpoints]

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
    mission_date: date = Field(..., description="Scheduled new date for the mission in managed airport local time")
    mission_time: time = Field(time(hour=datetime.now().hour, minute=datetime.now().minute), description="Scheduled new time for the mission in managed airport local time")
    queue: str = Field(..., description="Name of emission broadcast queue for positions")

    @validator('queue')
    def validate_queue(cls, queue):
        r = redis.Redis(**REDIS_CONNECT)
        valid_values = [q[0] for q in Queue.getCombo(r)]
        return LOV_Validator(value=queue,
                             valid_values=valid_values,
                             invalid_message=f"Invalid queue name {queue}")


class DeleteMission(BaseModel):

    mission_id: str = Field(..., description="Mission identifier")
    queue: str = Field(..., description="Name of emission broadcast queue for positions")

    @validator('queue')
    def validate_queue(cls, queue):
        r = redis.Redis(**REDIS_CONNECT)
        valid_values = [q[0] for q in Queue.getCombo(r)]
        return LOV_Validator(value=queue,
                             valid_values=valid_values,
                             invalid_message=f"Invalid queue name {queue}")


