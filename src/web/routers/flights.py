import json
from fastapi import APIRouter, Body, File
from fastapi.middleware.cors import CORSMiddleware

from datetime import datetime, date, time, timedelta
from typing import Optional, Literal, List

from pydantic import BaseModel, Field, validator

from emitpy.constants import ARRIVAL, DEPARTURE, EMIT_RATES


router = APIRouter(
    prefix="/flights",
    tags=["flights"],
    responses={404: {"description": "Not found"}},
)

class CreateFlight(BaseModel):
    airline: str = Field(..., description="Airline must be operating at managed airport")
    flight_number: str
    flight_date: date
    flight_time: time
    movement: Literal[ARRIVAL, DEPARTURE]
    airport: str
    ramp: str
    aircraft_type: str
    aircraft_reg: str
    call_sign: str
    icao24: str
    runway: str
    emit_rate: int
    queue: str
    create_services: bool

    @validator('airline')
    def validate_airline(cls,airline):
        airlines=["QR","SN"]
        return LOV_Validator(value=airline,
                             valid_values=airlines,
                             invalid_message=f"Airline code must be in {airlines}")

    @validator('emit_rate')
    def validate_emit_rate(cls,emit_rate):
        vv = [int(e[0]) for e in EMIT_RATES]
        return LOV_Validator(value=emit_rate,
                             valid_values=vv,
                             invalid_message=f"Emit rate value must be in {vv} (seconds)")


class ScheduleFlight(BaseModel):
    flight_id: str = Field(..., description="Flight IATA identifier")
    sync_name: str
    flight_date: datetime = Field(..., description="Scheduled new date and time for flight")

class ScheduleFlightServices(BaseModel):
    flight_id: str = Field(..., description="Flight IATA identifier")
    flight_date: datetime = Field(..., description="Scheduled date time for flight (arrival or departure), services will be scheduled according to PTS")


@router.get("/", tags=["flights"])
async def all_flights():
    return {
        "status": 0,
        "message": "not implemented",
        "data": None
    }

@router.post("/", tags=["flights"])
async def create_flight(
    flight_in: CreateFlight = Body(..., embed=True)
):
    return {
        "status": 0,
        "message": "not implemented",
        "data": flight_in
    }

@router.put("/", tags=["flights"])
async def schedule_flight(
    schedule_flight_id: ScheduleFlight = Body(..., embed=True)
):
    return {
        "status": 0,
        "message": "not implemented",
        "data": schedule_flight_id
    }

@router.delete("/{flight_id}", tags=["flights"])
async def delete_flight(
    flight_id: str
):
    return {
        "status": 0,
        "message": "not implemented",
        "data": flight_id
    }


