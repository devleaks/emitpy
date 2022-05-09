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
    request: Request, service_in: CreateService = Body(..., embed=True)
):
    ret = StatusInfo(status=1, message="exception", data=None)
    try:
        print(">>>>", service_in)
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
               service=service_in.service,
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
    request: Request, service_in: ScheduleService = Body(..., embed=True)
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
    request: Request, service_in: DeleteService = Body(..., embed=True)
):
    ret = StatusInfo(status=1, message="exception", data=None)
    try:
        ret = request.app.state.emitpy.do_delete(
                queue=service_in.queue,
                ident=service_in.service_id)
    except Exception as ex:
        ret = StatusInfo(status=1, message="exception", data=traceback.format_exc())

    return JSONResponse(content=jsonable_encoder(ret))


class CreateFlightServices(BaseModel):
    flight_id: str = Field(..., description="Flight IATA identifier")
    scheduled: datetime = Field(..., description="Scheduled new date and time for flight")
    emit_rate: int
    queue: str


# will be /services/flight/...
@router.post("/flight", tags=["flights", "services"])
async def create_fight_services(
    request: Request, fs_in: CreateFlightServices = Body(..., embed=True)
):
    # ret = StatusInfo(status=1, message="exception", data=None)
    # try:
    #     input_d = fs_in.service_date if fs_in.service_date is not None else datetime.now()
    #     input_t = fs_in.service_time if fs_in.service_time is not None else datetime.now()
    #     dt = datetime(year=input_d.year,
    #                   month=input_d.month,
    #                   day=input_d.day,
    #                   hour=input_t.hour,
    #                   minute=input_t.minute)
    #     ret = request.app.state.emitpy.do_flight_service(
    #             flight_id=fs_in.flight_id,
    #             scheduled=dt.isoformat(),
    #             emit_rate=fs_in.emit_rate,
    #             queue=fs_in.queue)
    # except Exception as ex:
    #     ret = StatusInfo(status=1, message="exception", data=traceback.format_exc())

    return JSONResponse(content=jsonable_encoder(NotAvailable()))


@router.put("/flight", tags=["flights", "services"])
async def schedule_fight_services(
    request: Request, fs_in: ScheduleFlightServices = Body(..., embed=True)
):
    return JSONResponse(content=jsonable_encoder(NotAvailable()))
