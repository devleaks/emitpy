import os
import csv
import json
import traceback

from fastapi import APIRouter, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from datetime import datetime, date, time, timedelta
from typing import Optional, Literal, List

from pydantic import BaseModel, Field, validator

from emitpy.constants import ARRIVAL, DEPARTURE, EMIT_RATES
from emitpy.aircraft import AircraftPerformance as Aircraft
from emitpy.airport import Airport
from emitpy.business import Airline
from emitpy.service import Service, ServiceVehicle, Mission, MissionVehicle
from ..models import NotAvailable


router = APIRouter(
    prefix="/airport",
    tags=["airport"],
    responses={
        404: {
            "description": "Not found"
        }
    }
)


templates = Jinja2Templates(directory="web/templates")


# ###############################
# Special lists for UI
#
@router.get("/airlines", tags=["reference"])
async def list_airlines(request: Request):
    return JSONResponse(content=Airline.getCombo(request.app.state.emitpy.redis))


@router.get("/airports", tags=["reference"])
async def list_airports(request: Request):
    return JSONResponse(content=Airport.getCombo(request.app.state.emitpy.redis))


@router.get("/airroutes-by-airport/{airport_iata}", tags=["reference"])
async def list_airroutes_by_airport(request: Request, airport_iata: str):
    return JSONResponse(content=request.app.state.emitpy.airport.manager.getAirrouteCombo(airport=airport_iata))


@router.get("/airroutes-by-airline/{airline_iata}", tags=["reference"])
async def list_airroutes_by_airline(request: Request, airline_iata: str):
    return JSONResponse(content=request.app.state.emitpy.airport.manager.getAirrouteCombo(airline=airline_iata))


@router.get("/ramps", tags=["reference"])
async def list_ramps(request: Request):
    return JSONResponse(content=request.app.state.emitpy.airport.getRampCombo())


@router.get("/runways", tags=["reference"])
async def list_runways(request: Request):
    return JSONResponse(content=request.app.state.emitpy.airport.getRunwayCombo())


@router.get("/pois", tags=["reference"])
async def list_points_of_interest(request: Request):
    return JSONResponse(content=request.app.state.emitpy.airport.getPOICombo())


@router.get("/checkpoints", tags=["reference"])
async def list_checkpoints(request: Request):
    return JSONResponse(content=request.app.state.emitpy.airport.getCheckpointCombo())


@router.get("/aircraft-types", tags=["reference"])
async def list_aircraft_types():
    return JSONResponse(content=Aircraft.getCombo())


@router.get("/service-types", tags=["reference", "services"])
async def list_services():
    return JSONResponse(content=Service.getCombo())


@router.get("/service-type-pois/{service_type}", tags=["reference", "services"])
async def list_service_type_pois(request: Request, service_type: str):
    return JSONResponse(content=request.app.state.emitpy.airport.getServicePoisCombo(service_type))


@router.get("/service-vehicle-models/{service}", tags=["reference", "services"])
async def list_service_vehicle_models(service: str):
    return JSONResponse(content=ServiceVehicle.getModels(service))


@router.get("/service-handlers", tags=["reference", "services"])
async def list_service_handlers(request: Request):
    return JSONResponse(content=request.app.state.emitpy.airport.manager.getCompaniesCombo(classId="Service"))


# @router.get("/service-depots")
# async def list_services():
#     return JSONResponse(content=Service.getCombo())


# @router.get("/service-rest-areas")
# async def list_services():
#     return JSONResponse(content=Service.getCombo())


@router.get("/mission-types", tags=["reference", "missions"])
async def list_services():
    return JSONResponse(content=Mission.getCombo())


@router.get("/mission-vehicle-models/", tags=["reference", "missions"])
async def list_service_vehicle_models():
    return JSONResponse(content=MissionVehicle.getCombo())


@router.get("/mission-handlers", tags=["reference", "missions"])
async def list_mission_handlers(request: Request):
    return JSONResponse(content=request.app.state.emitpy.airport.manager.getCompaniesCombo(classId="Mission"))


@router.get("/pias", tags=["flights", "services", "missions"])
async def list_enqueues(request: Request):
    return JSONResponse(content=request.app.state.emitpy.do_list_emit())


# ###############################
# Display allocations
#
@router.get("/allocation/runways", tags=["allocations"])
async def list_runways(request: Request):
    t = request.app.state.emitpy.airport.manager.runway_allocator.table()
    return JSONResponse(content=t)

@router.get("/allocation/runways-viewer", tags=["allocations"], include_in_schema=False)
async def allocation_ramps(request: Request):
    return templates.TemplateResponse("visavail.html", {"request": request, "alloc": "runways"})


# @router.get("/allocation/ramps", tags=["allocations"])
# async def list_ramps():
#     filename = os.path.join("..", "data", "managedairport", "OTHH", "flights", "2019_W15_ROTATION_RAW.csv")
#     file = open(filename, "r")
#     csvdata = csv.DictReader(file)
#     bays = {}
#     for r in csvdata:
#         bay = r["BAY_x"]
#         if bay not in bays.keys():
#             bays[bay] = {
#                 "measure": bay,
#                 "data": [],
#                 "description": [],
#                 "categories": {
#                     "11": { "class": "delay11" },
#                     "00": { "class": "delay00" },
#                     "10": { "class": "delay10" },
#                     "01": { "class": "delay01" }
#                 }
#             }
#         ontime  = float(r['FLIGHT TOTAL DELAY_x']) < 20
#         ontime2 = float(r['FLIGHT TOTAL DELAY_x']) < 20
#         ontimec = f"{1 if ontime else 0}{1 if ontime2 else 0}"
#         bays[bay]["data"].append([r['FLIGHT SCHEDULED TIME_x'], ontimec, r['FLIGHT SCHEDULED TIME_y']])
#         bays[bay]["description"].append(f"{r['AIRLINE CODE_x']}{r['FLIGHT NO_x']} ({r['AIRPORT_x']})"
#                                       + f" -> {r['AIRLINE CODE_y']}{r['FLIGHT NO_y']} ({r['AIRPORT_y']})")
#     bays = dict(sorted(bays.items()))  # sort by key=bay
#     return JSONResponse(content=list(bays.values()))

@router.get("/allocation/ramps", tags=["allocations"])
async def list_ramps(request: Request):
    t = request.app.state.emitpy.airport.manager.ramp_allocator.table()
    return JSONResponse(content=t)

@router.get("/allocation/ramps-viewer", tags=["allocations"], include_in_schema=False)
async def allocation_ramps(request: Request):
    return templates.TemplateResponse("visavail.html", {"request": request, "alloc": "ramps"})


@router.get("/allocation/vehicles", tags=["allocations"])
async def list_vehicles(request: Request):
    t = request.app.state.emitpy.airport.manager.vehicle_allocator.table()
    return JSONResponse(content=t)

@router.get("/allocation/vehicles-viewer", tags=["allocations"], include_in_schema=False)
async def allocation_vehicles(request: Request):
    return templates.TemplateResponse("visavail.html", {"request": request, "alloc": "vehicles"})


# ###############################
# Other general lists
#
@router.get("/flights", tags=["movements"])
async def list_flights(request: Request):
    t = request.app.state.emitpy.airport.manager.allFlights(request.app.state.emitpy.redis)
    return JSONResponse(content=list(t))

@router.get("/services/service/{service_type}", tags=["movements"])
async def list_services_by_type(request: Request, service_type: str):
    t = request.app.state.emitpy.airport.manager.allServiceOfType(redis=request.app.state.emitpy.redis, service_type=service_type)
    return JSONResponse(content=list(t))

@router.get("/services/ramp/{ramp_id}", tags=["movements"])
async def list_services_by_ramp(request: Request, ramp_id: str):
    t = request.app.state.emitpy.airport.manager.allServiceForRamp(redis=request.app.state.emitpy.redis, ramp_id=ramp_id)
    return JSONResponse(content=list(t))

@router.get("/missions", tags=["movements"])
async def list_missions(request: Request):
    t = request.app.state.emitpy.airport.manager.allMissions(request.app.state.emitpy.redis)
    return JSONResponse(content=list(t))

