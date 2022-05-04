import json
from fastapi import APIRouter, Body, File
from fastapi.middleware.cors import CORSMiddleware

from datetime import datetime, date, time, timedelta
from typing import Optional, Literal, List

from pydantic import BaseModel, Field, validator

from emitpy.constants import ARRIVAL, DEPARTURE, EMIT_RATES

router = APIRouter(
    prefix="/missions",
    tags=["missions"],
    responses={404: {"description": "Not found"}},
)

# ####################
# MISSIONS
#
class CreateMission(BaseModel):
    operator: str
    mission: str
    service_vehicle_type: str
    service_vehicle_reg: str
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
    sync_name: str
    mission_date: datetime = Field(..., description="New scheduled mission time")

@router.post("/", tags=["missions"])
async def create_mission(
    mission_in: CreateMission = Body(..., embed=True)
):
    return {
        "status": 0,
        "message": "not implemented",
        "data": mission_in
    }

@router.put("/", tags=["missions"])
async def schedule_mission(
    mission_in: ScheduleMission = Body(..., embed=True)
):
    return {
        "status": 0,
        "message": "not implemented",
        "data": mission_in
    }

@router.delete("/", tags=["missions"])
async def delete_mission(
    mission_in: str
):
    return {
        "status": 0,
        "message": "not implemented",
        "data": mission_in
    }
