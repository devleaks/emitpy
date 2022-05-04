import json
from fastapi import APIRouter, Body, File
from fastapi.middleware.cors import CORSMiddleware

from datetime import datetime, date, time, timedelta
from typing import Optional, Literal, List

from pydantic import BaseModel, Field, validator

from emitpy.constants import ARRIVAL, DEPARTURE, EMIT_RATES


router = APIRouter(
    prefix="/queues",
    tags=["queues"],
    responses={404: {"description": "Not found"}},
)

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


@router.post("/", tags=["queues"])
async def create_queue(
    queue_in: CreateQueue = Body(..., embed=True)
):
    return {
        "status": 0,
        "message": "not implemented",
        "data": queue_in
    }

@router.put("/", tags=["queues"])
async def schedule_queue(
    queue_in: ScheduleQueue = Body(..., embed=True)
):
    return {
        "status": 0,
        "message": "not implemented",
        "data": queue_in
    }

@router.delete("/", tags=["queues"])
async def delete_queue(
    queue_in: str
):
    return {
        "status": 0,
        "message": "not implemented",
        "data": queue_in
    }
