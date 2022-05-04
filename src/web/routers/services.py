import json
from fastapi import APIRouter, Body, File
from fastapi.middleware.cors import CORSMiddleware

from datetime import datetime, date, time, timedelta
from typing import Optional, Literal, List

from pydantic import BaseModel, Field, validator

from emitpy.constants import ARRIVAL, DEPARTURE, EMIT_RATES


router = APIRouter(
    prefix="/services",
    tags=["services"],
    responses={404: {"description": "Not found"}},
)



# ####################
# SERVICES
#
class CreateService(BaseModel):
    ramp: str
    aircraft_type: str
    handler: str
    service: str
    quantity: float
    service_vehicle_model: str
    service_vehicle_reg: str
    icao24: str
    service_pos: str
    previous_position: str
    next_position: str
    service_date: str
    service_time: str
    emit_rate: str
    queue: str

    @validator('emit_rate')
    def validate_emit_rate(cls,emit_rate):
        vv = [int(e[0]) for e in EMIT_RATES]
        return LOV_Validator(value=emit_rate,
                             valid_values=vv,
                             invalid_message=f"Emit rate value must be in {vv} (seconds)")


class ScheduleService(BaseModel):
    service_id: str = Field(..., description="Service identifier")
    sync_name: str
    service_date: datetime = Field(..., description="Scheduled service time")

@router.post("/", tags=["services"])
async def create_service(
    service_in: CreateService = Body(..., embed=True)
):
    return {
        "status": 0,
        "message": "not implemented",
        "data": service_in
    }

@router.put("/", tags=["services"])
async def schedule_service(
    service_in: ScheduleService = Body(..., embed=True)
):
    return {
        "status": 0,
        "message": "not implemented",
        "data": service_in
    }

@router.delete("/", tags=["services"])
async def delete_service(
    service_in: str
):
    return {
        "status": 0,
        "message": "not implemented",
        "data": service_in
    }


class CreateFlightServices(BaseModel):
    flight_id: str = Field(..., description="Flight IATA identifier")
    scheduled: datetime = Field(..., description="Scheduled new date and time for flight")
    emit_rate: int
    queue: str


@router.post("/flight/", tags=["flights", "services"])
async def create_fight_services(
    flight_in: CreateFlightServices = Body(..., embed=True)
):
    return {
        "status": 0,
        "message": "not implemented",
        "data": flight_in
    }

