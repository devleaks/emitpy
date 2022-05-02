import json
from fastapi import FastAPI, Body, File
from fastapi.middleware.cors import CORSMiddleware

from datetime import datetime, date, time, timedelta
from typing import Optional, Literal, List

from pydantic import BaseModel, Field, validator

from emitpy.constants import ARRIVAL, DEPARTURE, EMIT_RATES


description = """
**Emitpy** is an ADS-B Track Generator. With **Emitpy** you can generate ADS-B tracks for

 - Flights
 - Ground service vehicles
 - Vehicles executing « _missions_ » (surveillance, emergency, fire...)

The generator also allows you to control output queues (create, re-schedule, restart...)


## Flights


## Ground Services

You will be able to:

* **Create services** (_not implemented_).
* **Re-schedule services** (_not implemented_).


## Missions


## Queues


## Utility functions


(more blabla to come here soon. Trust me.)
"""


tags_metadata = [
    {
        "name": "flights",
        "description": "Operations with flights.",
    },
    {
        "name": "services",
        "description": "Operations with ground services."
    },
]


app = FastAPI(
    title="Emitpy REST API",
    description=description,
    version="0.1.0",
    license_info={
        "name": "MIT",
        "url": "https://mit-license.org",
    },
    openapi_tags=tags_metadata
)

app.add_middleware(CORSMiddleware,
                   allow_origins=["*"],
                   allow_credentials=True,
                   allow_methods=["*"],
                   allow_headers=["*"],)


@app.get("/")
async def root():
    return {
        "status": 1,
        "message": "emitpy REST API listening...",
        "data": None
    }


def LOV_Validator(
    value: str,
    valid_values: List[str],
    invalid_message: str) -> str:
    if value not in valid_values:
        raise ValueError(invalid_message)
    return value


# ####################
# FLIGHTS
#
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
    flight_date: datetime = Field(..., description="Scheduled new ETA for flight, services will be scheduled according to PTS")

@app.post("/flight", tags=["flights"])
async def create_flight(
    flight_in: CreateFlight = Body(..., embed=True)
):
    return {
        "status": 0,
        "message": "not implemented",
        "data": flight_in
    }

@app.put("/flight", tags=["flights"])
async def schedule_flight(
    flight_in: ScheduleFlight = Body(..., embed=True)
):
    return {
        "status": 0,
        "message": "not implemented",
        "data": flight_in
    }

@app.delete("/flight", tags=["flights"])
async def delete_flight(
    flight_in: str
):
    return {
        "status": 0,
        "message": "not implemented",
        "data": flight_in
    }


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

@app.post("/service", tags=["services"])
async def create_service(
    service_in: CreateService = Body(..., embed=True)
):
    return {
        "status": 0,
        "message": "not implemented",
        "data": service_in
    }

@app.put("/service", tags=["services"])
async def schedule_service(
    service_in: ScheduleService = Body(..., embed=True)
):
    return {
        "status": 0,
        "message": "not implemented",
        "data": service_in
    }

@app.delete("/service", tags=["services"])
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


@app.post("/flight-services", tags=["flights", "services"])
async def create_fight_services(
    flight_in: CreateFlightServices = Body(..., embed=True)
):
    return {
        "status": 0,
        "message": "not implemented",
        "data": flight_in
    }


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

@app.post("/mission", tags=["missions"])
async def create_mission(
    mission_in: CreateMission = Body(..., embed=True)
):
    return {
        "status": 0,
        "message": "not implemented",
        "data": mission_in
    }

@app.put("/mission", tags=["missions"])
async def schedule_mission(
    mission_in: ScheduleMission = Body(..., embed=True)
):
    return {
        "status": 0,
        "message": "not implemented",
        "data": mission_in
    }

@app.delete("/mission", tags=["missions"])
async def delete_mission(
    mission_in: str
):
    return {
        "status": 0,
        "message": "not implemented",
        "data": mission_in
    }


# ####################
# QUEUES
#
class CreateQueue(BaseModel):
    name: str
    formatter: str
    mission_date: datetime
    speed: float
    start: bool


class ScheduleQueue(BaseModel):
    queue_id: str = Field(..., description="Queue identifier")
    mission_date: datetime
    speed: float
    start: bool


@app.post("/queue", tags=["queues"])
async def create_queue(
    queue_in: CreateQueue = Body(..., embed=True)
):
    return {
        "status": 0,
        "message": "not implemented",
        "data": queue_in
    }

@app.put("/queue", tags=["queues"])
async def schedule_queue(
    queue_in: ScheduleQueue = Body(..., embed=True)
):
    return {
        "status": 0,
        "message": "not implemented",
        "data": queue_in
    }

@app.delete("/queue", tags=["queues"])
async def delete_queue(
    queue_in: str
):
    return {
        "status": 0,
        "message": "not implemented",
        "data": queue_in
    }


# ####################
# FLIGHT TABLE
#
@app.post("/flight-table/", tags=["operations"])
async def create_flight_table(file: bytes = File(...)):
    return {
        "status": 0,
        "message": "not implemented",
        "data": {"file_size": len(file)}
    }



# ####################
# LISTS
#
@app.get("/flights")
async def list_flights():
    return {
        "status": 0,
        "message": "not implemented",
        "data": {}
    }

@app.get("/services")
async def list_services(limit: int = 0):
    return {
        "status": 0,
        "message": "not implemented",
        "data": {
            "flight_id": flight_id,
            "service_type": service_type,
            "limit": limit
        }
    }

@app.get("/services/flight/{flight_id}")
async def list_services_by_flight(flight_id: str):
    return {
        "status": 0,
        "message": "not implemented",
        "data": {
            "flight_id": flight_id
        }
    }

@app.get("/services/service/{service_type}")
async def list_services_by_type(service_type: str):
    return {
        "status": 0,
        "message": "not implemented",
        "data": {
            "service_type": service_type
        }
    }

@app.get("/services/ramp/{ramp_id}")
async def list_services_by_ramp(ramp_id: str):
    return {
        "status": 0,
        "message": "not implemented",
        "data": {
            "ramp_id": ramp_id
        }
    }

@app.get("/missions")
async def list_missions():
    return {
        "status": 0,
        "message": "not implemented",
        "data": {}
    }

@app.get("/queues")
async def list_queues():
    return {
        "status": 0,
        "message": "not implemented",
        "data": {}
    }
