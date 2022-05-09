from datetime import datetime, date, time, timedelta
from typing import Optional, Literal, List

from pydantic import BaseModel, Field, validator

from emitpy.constants import EMIT_RATES
from .utils import LOV_Validator


class CreateService(BaseModel):
    ramp: str
    aircraft_type: str
    handler: str
    service: str
    quantity: float
    service_vehicle_model: str
    service_vehicle_reg: str
    icao24: str
    previous_position: str
    next_position: str
    service_date: date
    service_time: time
    emit_rate: int
    queue: str

    @validator('emit_rate')
    def validate_emit_rate(cls,emit_rate):
        vv = [int(e[0]) for e in EMIT_RATES]
        return LOV_Validator(value=emit_rate,
                             valid_values=vv,
                             invalid_message=f"Emit rate value must be in {vv} (seconds)")


class ScheduleService(BaseModel):
    service_id: str = Field(..., description="Service identifier")
    sync_name: str = Field(..., description="Name of synchronization mark for new date/time schedule")
    service_date: date = Field(..., description="Scheduled new date for the service")
    service_time: time = Field(..., description="Scheduled new time for the service")
    queue: str


class DeleteService(BaseModel):
    service_id: str = Field(..., description="Mission identifier")
    queue: str = Field(..., description="Destination queue")


class CreateFlightServices(BaseModel):
    flight_id: str = Field(..., description="Flight IATA identifier")
    emit_rate: str
    queue: str


class ScheduleFlightServices(BaseModel):
    flight_id: str = Field(..., description="Flight IATA identifier")
    flight_date: datetime = Field(..., description="Scheduled date time for flight (arrival or departure), services will be scheduled according to PTS")

