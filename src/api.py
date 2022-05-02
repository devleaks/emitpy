import json
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from datetime import datetime, date, time, timedelta
from typing import Optional

from pydantic import BaseModel, Field, validator

app = FastAPI()

app.add_middleware(CORSMiddleware,
                   allow_origins=["*"],
                   allow_credentials=True,
                   allow_methods=["*"],
                   allow_headers=["*"],)


@app.get("/")
async def root():
    return {
        "status": 1,
        "message": "hello, world",
        "data": None
    }

class CreateFlight:
    airline: str = Field(..., description="Airline must be operating at managed airport")
    @validator('airline')
    def validate_airline(cls,airline):
      airlines=['QR','SN','LH']
      if airline not in airlines:
        raise ValueError(f"Airline code must be in {airlines}")
      return airline

@app.post("/flight")
async def create_flight(
    airline: str,
    flight_number: str,
    flight_date: date,
    flight_time: time,
    movement: str,
    airport: str,
    ramp: str,
    aircraft_type: str,
    aircraft_reg: str,
    call_sign: str,
    icao24: str,
    runway: str,
    emit_rate: int,
    queue: str,
    create_services: bool
):
    return {
        "status": 0,
        "message": "not implemented",
        "data": None
    }

