from typing import Optional, Literal, List
from datetime import datetime, date, time, timedelta

from pydantic import BaseModel, Field, validator

from emitpy.constants import ARRIVAL, DEPARTURE, EMIT_RATES
from .utils import LOV_Validator


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
    sync_name: str = Field(..., description="Name of sychronization mark for new date time")
    flight_date: date = Field(..., description="Scheduled new date for flight")
    flight_time: time = Field(..., description="Scheduled new time for flight")
    queue: str = Field(..., description="Destination queue")

class DeleteFlight(BaseModel):
    flight_id: str = Field(..., description="Flight IATA identifier")
    queue: str = Field(..., description="Destination queue")
