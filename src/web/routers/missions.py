import json
import traceback

from fastapi import APIRouter, Request, Body
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from datetime import datetime, date, time, timedelta
from typing import Optional, Literal, List

from pydantic import BaseModel, Field, validator

from ..models import CreateMission, ScheduleMission, DeleteMission
from emitpy.constants import EMIT_RATES
from emitpy.emitapp import StatusInfo

router = APIRouter(
    prefix="/mission",
    tags=["missions"],
    responses={404: {"description": "Not found"}},
)

@router.post("/", tags=["missions"])
async def create_mission(
    request: Request, mission_in: CreateMission
):
    ret = StatusInfo(status=1, message="exception", data=None)
    try:
        input_d = mission_in.mission_date if mission_in.mission_date is not None else datetime.now()
        input_t = mission_in.mission_time if mission_in.mission_time is not None else datetime.now()
        dt = datetime(year=input_d.year,
                      month=input_d.month,
                      day=input_d.day,
                      hour=input_t.hour,
                      minute=input_t.minute)
        ret = request.app.state.emitpy.do_mission(
                queue=mission_in.queue,
                emit_rate=int(mission_in.emit_rate),
                operator=mission_in.operator,
                checkpoints=[],
                mission=mission_in.mission,
                vehicle_model=mission_in.mission_vehicle_type,
                vehicle_ident=mission_in.mission_vehicle_reg,
                vehicle_icao24=mission_in.icao24,
                vehicle_startpos=mission_in.previous_position,
                vehicle_endpos=mission_in.next_position,
                scheduled=dt.isoformat())
    except Exception as ex:
        ret = StatusInfo(status=1, message="exception", data=traceback.format_exc())

    return JSONResponse(content=jsonable_encoder(ret))


@router.put("/", tags=["missions"])
async def schedule_mission(
    request: Request, mission_in: ScheduleMission
):
    ret = StatusInfo(status=1, message="exception", data=None)
    try:
        input_d = mission_in.mission_date if mission_in.mission_date is not None else datetime.now()
        input_t = mission_in.mission_time if mission_in.mission_time is not None else datetime.now()
        dt = datetime(year=input_d.year,
                      month=input_d.month,
                      day=input_d.day,
                      hour=input_t.hour,
                      minute=input_t.minute)
        ret = request.app.state.emitpy.do_schedule(
                queue=mission_in.queue,
                ident=mission_in.mission_id,
                sync=mission_in.sync_name,
                scheduled=dt.isoformat())
    except Exception as ex:
        ret = StatusInfo(status=1, message="exception", data=traceback.format_exc())

    return JSONResponse(content=jsonable_encoder(ret))


@router.delete("/", tags=["missions"])
async def delete_mission(
    request: Request, mission_in: DeleteMission
):
    ret = StatusInfo(status=1, message="exception", data=None)
    try:
        ret = request.app.state.emitpy.do_delete(
                queue=mission_in.queue,
                ident=mission_in.mission_id)
    except Exception as ex:
        ret = StatusInfo(status=1, message="exception", data=traceback.format_exc())

    return JSONResponse(content=jsonable_encoder(ret))

