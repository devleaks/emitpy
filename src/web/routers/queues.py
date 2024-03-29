import json
import traceback

from fastapi import APIRouter, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from datetime import datetime, date, time, timedelta
from typing import Optional, Literal, List

from pydantic import BaseModel, Field, validator

from emitpy.constants import ARRIVAL, DEPARTURE, EMIT_RATES
from ..models import CreateQueue, ScheduleQueue, PiasEnqueue, EmitDifferent
from emitpy.emitapp import StatusInfo
from emitpy.broadcast import Format, Queue



router2 = APIRouter(
    prefix="/queues",
    tags=["queues"],
    responses={404: {"description": "Not found"}},
)

@router2.get("/", tags=["queues"])
async def list_queues(request: Request):
    return JSONResponse(content=Queue.getCombo(request.app.state.emitpy.redis))

@router2.get("/formats", tags=["queues"])
async def list_formats():
    return JSONResponse(content=Format.getCombo())



router = APIRouter(
    prefix="/queue",
    tags=["queues"],
    responses={404: {"description": "Not found"}},
)


@router.post("/", tags=["queues"])
async def create_queue(
    request: Request, queue_in: CreateQueue
):
    ret = StatusInfo(status=1, message="exception", data=None)
    try:
        input_d = queue_in.queue_date if queue_in.queue_date is not None else datetime.now()
        input_t = queue_in.queue_time if queue_in.queue_time is not None else datetime.now()
        dt = datetime(year=input_d.year,
                      month=input_d.month,
                      day=input_d.day,
                      hour=input_t.hour,
                      minute=input_t.minute)
        ret = request.app.state.emitpy.do_create_queue(
                name=queue_in.name,
                formatter=queue_in.formatter,
                starttime=dt.isoformat(),
                speed=float(queue_in.speed),
                start=queue_in.start)
    except Exception as ex:
        ret = StatusInfo(status=1, message="exception", data=traceback.format_exc())
    return JSONResponse(content=jsonable_encoder(ret))


@router.put("/", tags=["queues"])
async def schedule_queue(
    request: Request, queue_in: ScheduleQueue
):
    ret = StatusInfo(status=1, message="exception", data=None)
    try:
        input_d = queue_in.queue_date if queue_in.queue_date is not None else datetime.now()
        input_t = queue_in.queue_time if queue_in.queue_time is not None else datetime.now()
        dt = datetime(year=input_d.year,
                      month=input_d.month,
                      day=input_d.day,
                      hour=input_t.hour,
                      minute=input_t.minute)
        ret = request.app.state.emitpy.do_reset_queue(
                name=queue_in.name,
                starttime=dt.isoformat(),
                speed=float(queue_in.speed),
                start=queue_in.start)
    except Exception as ex:
        ret = StatusInfo(status=1, message="exception", data=traceback.format_exc())
    return JSONResponse(content=jsonable_encoder(ret))


@router.delete("/", tags=["queues"])
async def delete_queue(
    request: Request, name: str
):
    ret = StatusInfo(status=1, message="exception", data=None)
    try:
        ret = request.app.state.emitpy.do_delete_queue(name=name)
    except Exception as ex:
        ret = StatusInfo(status=1, message="exception", data=traceback.format_exc())
    return JSONResponse(content=jsonable_encoder(ret))


@router.put("/pias")
async def pias_enqueue(
    request: Request, enqueue_in: PiasEnqueue
):
    ret = StatusInfo(status=1, message="exception", data=None)
    try:
        ret = request.app.state.emitpy.do_pias_emit(
                ident=enqueue_in.enqueue_id,
                queue=enqueue_in.queue)
    except Exception as ex:
        ret = StatusInfo(status=1, message="exception", data=traceback.format_exc())
    return JSONResponse(content=jsonable_encoder(ret))


@router.put("/emitagain", tags=["movements"])
async def emit_different(
    request: Request, again_in: EmitDifferent
):
    ret = StatusInfo(status=1, message="exception", data=None)
    try:
        input_d = again_in.sync_date if again_in.sync_date is not None else datetime.now()
        input_t = again_in.sync_time if again_in.sync_time is not None else datetime.now()
        dt = datetime(year=input_d.year,
                      month=input_d.month,
                      day=input_d.day,
                      hour=input_t.hour,
                      minute=input_t.minute)
        ret = request.app.state.emitpy.do_emit_again(
                ident=again_in.emit_id,
                sync=again_in.sync_name,
                scheduled=dt.isoformat(),
                new_frequency=again_in.new_emit_rate,
                queue=again_in.queue)
    except Exception as ex:
        ret = StatusInfo(status=1, message="exception", data=traceback.format_exc())
    return JSONResponse(content=jsonable_encoder(ret))




