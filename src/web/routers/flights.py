import traceback

from fastapi import APIRouter, Request, Body
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from datetime import datetime, date, time, timedelta

from emitpy.emitapp import StatusInfo

from ..models import CreateFlight, ScheduleFlight, DeleteFlight, NotAvailable


router = APIRouter(
    prefix="/flight",
    tags=["flights"],
    responses={404: {"description": "Not found"}},
)


# @router.get("/", tags=["flights"])
# async def all_flights():
#     return JSONResponse(content=jsonable_encoder(NotAvailable()))


@router.post("/", tags=["flights"])
async def create_flight(
    request: Request, flight_in: CreateFlight
):
    ret = StatusInfo(status=1, message="exception", data=None)
    try:
        input_d = flight_in.flight_date if flight_in.flight_date is not None else datetime.now()
        input_t = flight_in.flight_time if flight_in.flight_time is not None else datetime.now()
        dt = datetime(year=input_d.year,
                      month=input_d.month,
                      day=input_d.day,
                      hour=input_t.hour,
                      minute=input_t.minute)
        at = None
        if flight_in.flight_actual_date is not None and flight_in.flight_actual_time is not None:
            at = datetime(year=flight_in.flight_actual_date.year,
                          month=flight_in.flight_actual_date.month,
                          day=flight_in.flight_actual_date.day,
                          hour=flight_in.flight_actual_time.hour,
                          minute=flight_in.flight_actual_time.minute).isoformat()
        ret = request.app.state.emitpy.do_flight(
                queue=flight_in.queue,
                emit_rate=int(flight_in.emit_rate),
                airline=flight_in.airline,
                flightnumber=flight_in.flight_number,
                scheduled=dt.isoformat(),
                apt=flight_in.airport,
                movetype=flight_in.movement,
                actype=flight_in.aircraft_type,
                ramp=flight_in.ramp,
                icao24=flight_in.icao24,
                acreg=flight_in.aircraft_reg,
                runway=flight_in.runway,
                is_cargo=flight_in.is_cargo,
                load_factor=flight_in.load_factor,
                do_services=flight_in.create_services,
                actual_datetime=at)
    except Exception as ex:
        ret = StatusInfo(status=1, message="exception", data=traceback.format_exc())

    return JSONResponse(content=jsonable_encoder(ret))


@router.put("/", tags=["flights"])
async def schedule_flight(
    request: Request, flight_in: ScheduleFlight
):
    ret = StatusInfo(status=1, message="exception", data=None)
    try:
        input_d = flight_in.flight_date if flight_in.flight_date is not None else datetime.now()
        input_t = flight_in.flight_time if flight_in.flight_time is not None else datetime.now()
        dt = datetime(year=input_d.year,
                      month=input_d.month,
                      day=input_d.day,
                      hour=input_t.hour,
                      minute=input_t.minute)
        ret = request.app.state.emitpy.do_schedule(
                queue=flight_in.queue,
                ident=flight_in.flight_id,
                sync=flight_in.sync_name,
                scheduled=dt.isoformat())
    except Exception as ex:
        ret = StatusInfo(status=1, message="exception", data=traceback.format_exc())

    return JSONResponse(content=jsonable_encoder(ret))


@router.delete("/", tags=["flights"])
async def delete_flight(
    request: Request, flight_in: DeleteFlight
):
    ret = StatusInfo(status=1, message="exception", data=None)
    try:
        ret = request.app.state.emitpy.do_delete(
                ident=flight_in.flight_id,
                queue=flight_in.queue,
                do_services=flight_in.delete_services)
    except Exception as ex:
        ret = StatusInfo(status=1, message="exception", data=traceback.format_exc())

    return JSONResponse(content=jsonable_encoder(ret))
