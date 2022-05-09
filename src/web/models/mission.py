from datetime import datetime, date, time, timedelta
from typing import Optional, Literal, List

from pydantic import BaseModel, Field, validator

from emitpy.constants import EMIT_RATES
from .utils import LOV_Validator


class CreateMission(BaseModel):
    operator: str
    mission: str
    mission_vehicle_type: str
    mission_vehicle_reg: str
    icao24: str
    previous_position: str
    next_position: str
    mission_date: date
    mission_time: time
    emit_rate: int
    queue: str

    @validator('emit_rate')
    def validate_emit_rate(cls,emit_rate):
        vv = [int(e[0]) for e in EMIT_RATES]
        return LOV_Validator(value=emit_rate,
                             valid_values=vv,
                             invalid_message=f"Emit rate value must be in {vv} (seconds)")


class ScheduleMission(BaseModel):
    mission_id: str = Field(..., description="Mission identifier")
    sync_name: str = Field(..., description="Name of synchronization mark for new date/time schedule")
    mission_date: date = Field(..., description="Scheduled new date for the mission")
    mission_time: time = Field(..., description="Scheduled new time for the mission")
    queue: str = Field(..., description="Destination queue of mission emission")


class DeleteMission(BaseModel):
    mission_id: str = Field(..., description="Mission identifier")
    queue: str = Field(..., description="Destination queue")
