import json
from fastapi import APIRouter, Body, File
from fastapi.middleware.cors import CORSMiddleware

from datetime import datetime, date, time, timedelta
from typing import Optional, Literal, List

from pydantic import BaseModel, Field, validator

from emitpy.constants import ARRIVAL, DEPARTURE, EMIT_RATES


router = APIRouter(
    prefix="/airport",
    tags=["airport"],
    responses={404: {"description": "Not found"}},
)

@router.get("/flights")
async def list_flights():
    return {
        "status": 0,
        "message": "not implemented",
        "data": {}
    }

@router.get("/services")
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

@router.get("/services/flight/{flight_id}")
async def list_services_by_flight(flight_id: str):
    return {
        "status": 0,
        "message": "not implemented",
        "data": {
            "flight_id": flight_id
        }
    }

@router.get("/services/service/{service_type}")
async def list_services_by_type(service_type: str):
    return {
        "status": 0,
        "message": "not implemented",
        "data": {
            "service_type": service_type
        }
    }

@router.get("/services/ramp/{ramp_id}")
async def list_services_by_ramp(ramp_id: str):
    return {
        "status": 0,
        "message": "not implemented",
        "data": {
            "ramp_id": ramp_id
        }
    }

@router.get("/missions")
async def list_missions():
    return {
        "status": 0,
        "message": "not implemented",
        "data": {}
    }

@router.get("/queues")
async def list_queues():
    return {
        "status": 0,
        "message": "not implemented",
        "data": {}
    }

@router.get("/runways")
async def list_runways():
    return {
        "status": 0,
        "message": "not implemented",
        "data": {}
    }

@router.get("/ramps")
async def list_ramps():
    return {
        "status": 0,
        "message": "not implemented",
        "data": {}
    }

@router.get("/ramps")
async def list_vehicles():
    return {
        "status": 0,
        "message": "not implemented",
        "data": {}
    }

