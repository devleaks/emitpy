import json
import traceback

from fastapi import APIRouter, Request, Body
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from datetime import datetime, date, time, timedelta
from typing import Optional, Literal, List

from pydantic import BaseModel, Field, validator

from ..models import CreateService, ScheduleService, DeleteService, NotAvailable
from ..models import CreateFlightServices, ScheduleFlightServices
from emitpy.constants import EMIT_RATES
from emitpy.emitapp import StatusInfo


router = APIRouter(
    prefix="/service",
    tags=["services"],
    responses={404: {"description": "Not found"}},
)


@router.post("/", tags=["services"])
async def create_service(
    request: Request, service_in: CreateService
):
    ret = StatusInfo(status=1, message="exception", data=None)
    try:
        input_d = service_in.service_date if service_in.service_date is not None else datetime.now()
        input_t = service_in.service_time if service_in.service_time is not None else datetime.now()
        dt = datetime(year=input_d.year,
                      month=input_d.month,
                      day=input_d.day,
                      hour=input_t.hour,
                      minute=input_t.minute)
        ret = request.app.state.emitpy.do_service(
               queue=service_in.queue,
               emit_rate=int(service_in.emit_rate),
               operator=service_in.handler,
               service=service_in.service_type,
               quantity=service_in.quantity,
               ramp=service_in.ramp,
               aircraft=service_in.aircraft_type,
               vehicle_model=service_in.service_vehicle_model,
               vehicle_ident=service_in.service_vehicle_reg,
               vehicle_icao24=service_in.icao24,
               vehicle_startpos=service_in.previous_position,
               vehicle_endpos=service_in.next_position,
               scheduled=dt.isoformat())
    except Exception as ex:
        ret = StatusInfo(status=1, message="exception", data=traceback.format_exc())

    return JSONResponse(content=jsonable_encoder(ret))


@router.put("/", tags=["services"])
async def schedule_service(
    request: Request, service_in: ScheduleService
):
    ret = StatusInfo(status=1, message="exception", data=None)
    try:
        input_d = service_in.service_date if service_in.service_date is not None else datetime.now()
        input_t = service_in.service_time if service_in.service_time is not None else datetime.now()
        dt = datetime(year=input_d.year,
                      month=input_d.month,
                      day=input_d.day,
                      hour=input_t.hour,
                      minute=input_t.minute)
        ret = request.app.state.emitpy.do_schedule(
                queue=service_in.queue,
                ident=service_in.service_id,
                sync=service_in.sync_name,
                scheduled=dt.isoformat())
    except Exception as ex:
        ret = StatusInfo(status=1, message="exception", data=traceback.format_exc())

    return JSONResponse(content=jsonable_encoder(ret))


@router.delete("/", tags=["services"])
async def delete_service(
    request: Request, service_in: DeleteService
):
    ret = StatusInfo(status=1, message="exception", data=None)
    try:
        ret = request.app.state.emitpy.do_delete(
                queue=service_in.queue,
                ident=service_in.service_id)
    except Exception as ex:
        ret = StatusInfo(status=1, message="exception", data=traceback.format_exc())

    return JSONResponse(content=jsonable_encoder(ret))


@router.get("/flight/{flight_id}", tags=["flights", "services"])
async def list_services_by_flight(request: Request, flight_id: str):
    t = request.app.state.emitpy.airport.manager.allServiceForFlight(redis=request.app.state.emitpy.redis, flight_id=flight_id)
    return JSONResponse(content=list(t))


@router.post("/flight", tags=["flights", "services"])
async def create_fight_services(
    request: Request, fs_in: CreateFlightServices
):
    ret = StatusInfo(status=1, message="exception", data=None)
    try:
        ret = request.app.state.emitpy.do_flight_services(
                flight_id=fs_in.flight_id,
                operator=fs_in.handler,
                emit_rate=fs_in.emit_rate,
                queue=fs_in.queue)
    except Exception as ex:
        ret = StatusInfo(status=1, message="exception", data=traceback.format_exc())

    return JSONResponse(content=jsonable_encoder(ret))


@router.put("/flight", tags=["flights", "services"])
async def schedule_fight_services(
    request: Request, fs_in: ScheduleFlightServices
):
    return JSONResponse(content=jsonable_encoder(NotAvailable("ScheduleFlightServices")))
