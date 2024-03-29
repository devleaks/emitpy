# API startup
# Start with
# uvicorn --reload --reload-dir ./emitpy api:app
import json
import logging
import coloredlogs
import uvicorn

import fastapi
import starlette.status as status

from fastapi import FastAPI, Body, File, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from web.routers import flights, services, missions, queues, airport
from fastapi_simple_security import api_key_router, api_key_security

import emitpy
from emitpy.parameters import MANAGED_AIRPORT_ICAO, SECURE_API, ALLOW_KEYGEN
from emitpy.emitapp import EmitApp
from emitpy.broadcast import Hypercaster


# #########################
# COLORFUL LOGGING
#
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("api")
logging.addLevelName(5, "spam")

coloredlogs.DEFAULT_FIELD_STYLES["levelname"] = {"color": "blue"}
coloredlogs.DEFAULT_FIELD_STYLES["name"] = {"color": "white", "bold": False, "bright": True}
coloredlogs.DEFAULT_FIELD_STYLES["asctime"] = {"color": 60, "bold": False, "bright": False}
coloredlogs.DEFAULT_FIELD_STYLES["name"] = {"color": 120, "bold": False, "bright": True}

coloredlogs.DEFAULT_LEVEL_STYLES["spam"] = {"color": "red"}
coloredlogs.DEFAULT_LEVEL_STYLES["info"] = {"color": 159, "bright": True}
coloredlogs.DEFAULT_LEVEL_STYLES["debug"] = {"color": "white"}  # , "faint": True

# coloredlogs.DEFAULT_FIELD_STYLES = {
#     'asctime': {
#         'color': 'green'
#     },
#     'hostname': {
#         'color': 'magenta'
#     },
#     'levelname': {
#         'bold': True,
#         'color': 'black'
#     },
#     'name': {
#         'color': 'blue'
#     },
#     'programname': {
#         'color': 'cyan'
#     },
#     'username': {
#         'color': 'yellow'
#     }
# }
# coloredlogs.DEFAULT_LEVEL_STYLES = {
#     'critical': {
#         'bold': True,
#         'color': 'red'
#     },
#     'debug': {
#         'color': 'green'
#     },
#     'error': {
#         'color': 'red'
#     },
#     'info': {},
#     'notice': {
#         'color': 'magenta'
#     },
#     'spam': {
#         'color': 'green',
#         'faint': True
#     },
#     'success': {
#         'bold': True,
#         'color': 'green'
#     },
#     'verbose': {
#         'color': 'blue'
#     },
#     'warning': {
#         'color': 'yellow'
#     }
# }

# %(levelname)s
coloredlogs.install(level=logging.DEBUG, logger=logger, fmt="%(asctime)s %(name)s:%(message)s", datefmt="%H:%M:%S")



# #########################
# REST API
#
description = """
**Emitpy** is an ADS-B Track Generator. With **Emitpy** you can generate ADS-B tracks for

 - Flights
 - Ground service equipments
 - Vehicles executing « _missions_ » (surveillance, emergency, fire...)

Emission of those vehicle positions is done on "output queues".

For each queue, it is possible to choose
 - the format of data that is produced
 - the rate of emissions (from 1 per second to 1 per hour)
 - the start date and time of the queue
 - the speed of emission, either slower or faster (up to 10 times) than actual time

The generator allows you to create, reset, start or stop output queues,
and precise its start date time, its speed of emission, and the data format of the emission.


## Flights

- Create a new flight (optionally with all its associated services)
- Re-schedule a flight (optionally with all its associated services)
- Suppress a flight


## Ground Services

- Create a single service
- Create services for a given flight
- Reschedule an existing service
- Suppress a service


## Missions

- Create a mission
- Reschedule a mission
- Suppress a mission


## All Movments

- Create another emission with different emission rate and enqueue to a different queue _(emit different)_
- Re-enqueued (restart) an emission _(pias)_


## Queues

- Create a queue
- Change queue timing parameters, reset, start or stop a queue
- Delete a queue


## Airport utility functions

- List all flights
- List all services, equipment types, equipment models, equipments in use
- List all missions, mission types and mission vehicles
- Show allocations for runways, ramps, and all equipments
- Helper functions to ease use interface building and selection by returning
  lists of pairs (internal_name, display_name) for combo boxes and form validation.


You're cleared for take off. Have a nice day.
"""

tags_metadata = [
    {
        "name": "flights",
        "description": "Operations with flights.",
    },
    {
        "name": "services",
        "description": "Operations with ground services."
    },
    {
        "name": "missions",
        "description": "Mission-related operations."
    },
    {
        "name": "queues",
        "description": "Queue operations: Creation, modification, reset, etc."
    },
    {
        "name": "airport",
        "description": "General airport queries: Allocations, flights, missions, etc. " +
        "but also airlines operating at the airport, connected airports, operators, handlers..."
    }
]

logger.info(f":init {emitpy.__NAME__} {emitpy.__COPYRIGHT__}")
logger.info(f":init Usable under Licence {emitpy.__LICENSE__} {emitpy.__LICENSEURL__}")

app = FastAPI(
    title="Emitpy REST API",
    description=description,
    version=emitpy.__version__ + " «" + emitpy.__version_name__ + "»",
    license_info={
        "name": emitpy.__LICENSE__,
        "url": emitpy.__LICENSEURL__
    },
    openapi_tags=tags_metadata
)

app.add_middleware(CORSMiddleware,
                   allow_origins=["*"],
                   allow_credentials=True,
                   allow_methods=["*"],
                   allow_headers=["*"])

if SECURE_API:  # See https://github.com/mrtolkien/fastapi_simple_security on how to use
    if ALLOW_KEYGEN:
        app.include_router(api_key_router, prefix="/auth", tags=["_auth"]) # , include_in_schema=False
        logger.warning(f":init {emitpy.__version__} «{emitpy.__version_name__}» key generation permitted")
    dependencies=[Depends(api_key_security)]
else:
    dependencies=[]

logger.info(f":init {emitpy.__version__} «{emitpy.__version_name__}» {'with' if SECURE_API else 'without'} security")

app.include_router(flights.router, dependencies=dependencies)
app.include_router(services.router, dependencies=dependencies)
app.include_router(missions.router, dependencies=dependencies)
app.include_router(airport.router, dependencies=dependencies)
app.include_router(airport.router2, dependencies=[])  # temporarily no security on allocation viewer

app.include_router(queues.router2, dependencies=dependencies)
app.include_router(queues.router, dependencies=dependencies)

app.mount("/static", StaticFiles(directory="web/static"), name="static")


@app.get("/", tags=["emitpy"], include_in_schema=False)
async def root():
    return fastapi.responses.RedirectResponse(
        "/docs",
        status_code=status.HTTP_302_FOUND)


APP_NAME = f"{emitpy.__version__} «{emitpy.__version_name__}»"


@app.on_event("startup")
async def startup():
    logger.info(f"{APP_NAME} cleared for take off..")
    # should collect and display:
    # git describe --tags
    # git log -1 --format=%cd --relative-date
    # + redis_connect info
    logger.info(f"{APP_NAME} taking off from «{MANAGED_AIRPORT_ICAO}»..")
    app.state.emitpy = EmitApp(MANAGED_AIRPORT_ICAO)
    if app.state.emitpy.use_redis() is not None:
        logger.info(f"{APP_NAME} ..positive climb. gear up. Starting hypercaster..")
        app.state.hypercaster = Hypercaster()
        logger.info(f"{APP_NAME} ..hypercaster running")
    else:
        logger.info(f"{APP_NAME} ..positive climb. gear up.")
        logger.warning(f"{APP_NAME} No Redis, no queue, file storage only.")


@app.on_event("shutdown")
async def shutdown():
    logger.info(f":shutdown {APP_NAME} cleared for landing..")
    if app.state.emitpy.use_redis() is not None:
        app.state.hypercaster.shutdown()  # shutdown last as it might not terminate properly...
        logger.info(f":shutdown {APP_NAME} ..final..")
    logger.info(f":shutdown {APP_NAME} ..landed. taxiing to gate..")
    app.state.emitpy.shutdown()
    logger.info(f":shutdown {APP_NAME} ..on block")
    logger.info(f":shutdown kiss landed at «{MANAGED_AIRPORT_ICAO}». Have a nice day.")


if __name__ == "__main__":
    uvicorn.run(app,
                host="localhost",
                port=8000,
                log_level="info",
                reload_dirs=["emitpy", "web"])
