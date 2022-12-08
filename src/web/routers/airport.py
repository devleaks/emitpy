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

from emitpy.constants import ARRIVAL, DEPARTURE, EMIT_RATES, REDIS_DATABASE, REDIS_TYPE
from emitpy.private import API_KEY
from emitpy.aircraft import AircraftTypeWithPerformance as Aircraft
from emitpy.airport import Airport
from emitpy.business import Airline
from emitpy.service import Service, Equipment, Mission, MissionVehicle
from ..models import NotAvailable


router = APIRouter(
    prefix="/airport",
#    tags=["airport"],
    responses={
        404: {
            "description": "Not found"
        }
    }
)

router2 = APIRouter(
    prefix="/allocation",
    tags=["allocations"],
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
@router.get("/airlines", tags=["reference", "airport"])
async def list_airlines(request: Request):
    return JSONResponse(content=Airline.getCombo(request.app.state.emitpy.redis))


@router.get("/airports", tags=["reference"])
async def list_airports(request: Request):
    return JSONResponse(content=Airport.getCombo(request.app.state.emitpy.redis))


@router.get("/airroutes-by-airport/{airport_iata}", tags=["reference"])
async def list_airroutes_by_airport(request: Request, airport_iata: str):
    return JSONResponse(content=request.app.state.emitpy.airport.manager.getAirrouteCombo(airport=airport_iata, redis=request.app.state.emitpy.redis))


@router.get("/airroutes-by-airline/{airline_iata}", tags=["reference"])
async def list_airroutes_by_airline(request: Request, airline_iata: str):
    return JSONResponse(content=request.app.state.emitpy.airport.manager.getAirrouteCombo(airline=airline_iata, redis=request.app.state.emitpy.redis))


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
async def list_aircraft_types(request: Request):
    return JSONResponse(content=Aircraft.getCombo(redis=request.app.state.emitpy.redis))


@router.get("/service-types", tags=["reference", "services"])
async def list_service_types():
    return JSONResponse(content=Service.getCombo())


@router.get("/service-type-pois/{service_type}", tags=["reference", "services"])
async def list_service_type_pois(request: Request, service_type: str):
    return JSONResponse(content=request.app.state.emitpy.airport.getServicePoisCombo(service=service_type))


@router.get("/service-type-depots/{service_type}", tags=["reference", "services"])
async def list_service_type_pois(request: Request, service_type: str):
    return JSONResponse(content=request.app.state.emitpy.airport.getDepotNames(service_name=service_type))


@router.get("/service-type-restareas/{service_type}", tags=["reference", "services"])
async def list_service_type_pois(request: Request, service_type: str):
    return JSONResponse(content=request.app.state.emitpy.airport.getRestAreaNames(service_name=service_type))


@router.get("/service-equipment-models/{service_type}", tags=["reference", "services"])
async def list_equipment_models(request: Request, service_type: str):
    return JSONResponse(content=Equipment.getModels(service_type))


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
async def list_mission_types():
    return JSONResponse(content=Mission.getCombo())


@router.get("/mission-vehicle-models/", tags=["reference", "missions"])
async def list_mission_vehicle_models():
    return JSONResponse(content=MissionVehicle.getCombo())


@router.get("/mission-handlers", tags=["reference", "missions"])
async def list_mission_handlers(request: Request):
    return JSONResponse(content=request.app.state.emitpy.airport.manager.getCompaniesCombo(classId="Mission"))


# ###############################
# Emits and Enqueues
#
@router.get("/pias", tags=["movements"])
async def list_enqueues(request: Request):
    return JSONResponse(content=request.app.state.emitpy.do_list())

@router.get("/pias/flights", tags=["flights"])
async def list_flight_enqueues(request: Request):
    return JSONResponse(content=request.app.state.emitpy.do_list(rtype=REDIS_TYPE.QUEUE.value, mtype=REDIS_DATABASE.FLIGHTS.value))

@router.get("/pias/services", tags=["services"])
async def list_service_enqueues(request: Request):
    return JSONResponse(content=request.app.state.emitpy.do_list(rtype=REDIS_TYPE.QUEUE.value, mtype=REDIS_DATABASE.SERVICES.value))

@router.get("/pias/missions", tags=["missions"])
async def list_mission_enqueues(request: Request):
    return JSONResponse(content=request.app.state.emitpy.do_list(rtype=REDIS_TYPE.QUEUE.value, mtype=REDIS_DATABASE.MISSIONS.value))

@router.get("/emit/flights", tags=["flights", "movements"])
async def list_flight_emits(request: Request):
    return JSONResponse(content=request.app.state.emitpy.do_list(rtype=REDIS_TYPE.EMIT.value, mtype=REDIS_DATABASE.FLIGHTS.value))

@router.get("/emit/services", tags=["services", "movements"])
async def list_service_emits(request: Request):
    return JSONResponse(content=request.app.state.emitpy.do_list(rtype=REDIS_TYPE.EMIT.value, mtype=REDIS_DATABASE.SERVICES.value))

@router.get("/emit/missions", tags=["missions", "movements"])
async def list_mission_emits(request: Request):
    return JSONResponse(content=request.app.state.emitpy.do_list(rtype=REDIS_TYPE.EMIT.value, mtype=REDIS_DATABASE.MISSIONS.value))

@router.get("/emit/syncmarks/{ident}", tags=["movements"])
async def list_syncmarks_for_emit(request: Request, ident: str):
    return JSONResponse(content=request.app.state.emitpy.list_syncmarks(ident))


# ###############################
# Display allocations
#
def reformat_allocations(alloc):
    def reformat(d):
        td = datetime.fromisoformat(d)
        return td.strftime("%Y-%m-%d %H:%M:00")

    table = {}
    for r in alloc:
        for a in alloc[r]:
            if r not in table.keys():
                table[r] = {
                    "measure": r,
                    "data": [],
                    "description": [],
                    "categories": {
                        "11": { "class": "delay11" },
                        "00": { "class": "delay00" },
                        "10": { "class": "delay10" },
                        "01": { "class": "delay01" }
                    }
                }
            ontimec = "11"
            table[r]["data"].append([reformat(a[0]), ontimec, reformat(a[1])])
            table[r]["description"].append(a[2])
    table = dict(sorted(table.items()))  # sort by key=r
    return list(table.values())

@router.get("/allocation/runways")
async def list_runways(request: Request):
    r0 = request.app.state.emitpy.airport.manager.runway_allocator.table()
    r1 = reformat_allocations(r0)
    return JSONResponse(content=r1)

@router.get("/allocation/equipments")
async def list_equipments(request: Request):
    r0 = request.app.state.emitpy.airport.manager.equipment_allocator.table()
    r1 = reformat_allocations(r0)
    return JSONResponse(content=r1)

@router.get("/allocation/ramps")
async def list_ramps(request: Request):
    r0 = request.app.state.emitpy.airport.manager.ramp_allocator.table()
    r1 = reformat_allocations(r0)
    return JSONResponse(content=r1)


# No API key for these pages:
@router2.get("/runways-viewer", include_in_schema=False)
async def allocation_runways(request: Request):
    return templates.TemplateResponse("visavail.html", {"request": request, "alloc": "runways", "api_key": API_KEY})

@router2.get("/ramps-viewer", include_in_schema=False)
async def allocation_ramps(request: Request):
    return templates.TemplateResponse("visavail.html", {"request": request, "alloc": "ramps", "api_key": API_KEY})

@router2.get("/equipments-viewer", include_in_schema=False)
async def allocation_equipments(request: Request):
    return templates.TemplateResponse("visavail.html", {"request": request, "alloc": "equipments", "api_key": API_KEY})


# ###############################
# Other general lists
#
@router.get("/flights", tags=["movements", "airport"])
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

