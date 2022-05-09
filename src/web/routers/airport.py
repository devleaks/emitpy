import os
import csv
import json
from fastapi import APIRouter, Body, File, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse

from datetime import datetime, date, time, timedelta
from typing import Optional, Literal, List

from pydantic import BaseModel, Field, validator

from emitpy.constants import ARRIVAL, DEPARTURE, EMIT_RATES


router = APIRouter(
    prefix="/airport",
    tags=["airport"],
    responses={404: {"description": "Not found"}},
)


templates = Jinja2Templates(directory="web/templates")


# ###############################@
# Display allocations
#
@router.get("/runways")
async def list_runways():
    return JSONResponse(content=list(runways.values()))

@router.get("/allocation/runways")
async def allocation_ramps(request: Request):
    return templates.TemplateResponse("visavail.html", {"request": request, "alloc": "runways"})


@router.get("/ramps")
async def list_ramps():
    filename = os.path.join("..", "data", "managedairport", "OTHH", "flights", "2019_W15_ROTATION_RAW.csv")
    file = open(filename, "r")
    csvdata = csv.DictReader(file)
    bays = {}
    for r in csvdata:
        bay = r["BAY_x"]
        if bay not in bays.keys():
            bays[bay] = {
                "measure": bay,
                "data": [],
                "description": [],
                "categories": {
                    "11": { "class": "delay11" },
                    "00": { "class": "delay00" },
                    "10": { "class": "delay10" },
                    "01": { "class": "delay01" }
                }
            }
        ontime  = float(r['FLIGHT TOTAL DELAY_x']) < 20
        ontime2 = float(r['FLIGHT TOTAL DELAY_x']) < 20
        ontimec = f"{1 if ontime else 0}{1 if ontime2 else 0}"
        bays[bay]["data"].append([r['FLIGHT SCHEDULED TIME_x'], ontimec, r['FLIGHT SCHEDULED TIME_y']])
        bays[bay]["description"].append(f"{r['AIRLINE CODE_x']}{r['FLIGHT NO_x']} ({r['AIRPORT_x']})"
                                      + f" -> {r['AIRLINE CODE_y']}{r['FLIGHT NO_y']} ({r['AIRPORT_y']})")
    bays = dict(sorted(bays.items()))  # sort by key=bay
    return JSONResponse(content=list(bays.values()))

@router.get("/allocation/ramps")
async def allocation_ramps(request: Request):
    return templates.TemplateResponse("visavail.html", {"request": request, "alloc": "ramps"})


@router.get("/vehicles")
async def list_ramps():
    return JSONResponse(content=list(vehicles.values()))

@router.get("/allocation/vehicles")
async def allocation_ramps(request: Request):
    return templates.TemplateResponse("visavail.html", {"request": request, "alloc": "vehicles"})




# ###############################@
# Special lists for UI
#



# ###############################@
# Other general lists
#
@router.get("/runways")

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


