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
from emitpy.parameters import MANAGED_AIRPORT, SECURE_API, ALLOW_KEYGEN
from emitpy.emitapp import EmitApp
from emitpy.emit import Hypercaster


# #########################
# COLORFUL LOGGING
#
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("api")
logging.addLevelName(5, "spam")

coloredlogs.DEFAULT_FIELD_STYLES["levelname"] = {"color": "blue"}
coloredlogs.DEFAULT_FIELD_STYLES["name"] = {"color": "white", "bold": False, "bright": True}

coloredlogs.DEFAULT_LEVEL_STYLES["spam"] = {"color": "red"}
coloredlogs.DEFAULT_LEVEL_STYLES["info"] = {"color": "cyan", "bright": True}
coloredlogs.DEFAULT_LEVEL_STYLES["debug"] = {"color": "white"}

# %(levelname)s
coloredlogs.install(level=logging.DEBUG, logger=logger, fmt="%(asctime)s %(name)s%(message)s", datefmt="%H:%M:%S")



# #########################
# REST API
#
description = """
**Emitpy** is an ADS-B Track Generator. With **Emitpy** you can generate ADS-B tracks for

 - Flights
 - Ground service vehicles
 - Vehicles executing « _missions_ » (surveillance, emergency, fire...)

Emission of those vehicle positions is done on "output queues".
For each queue, it is possible to choose
 - the format of data
 - the rate of emissions
 - the start date time of the queue
 - the speed of emission, either slower or fater than actual time

The generator allows you to create, reset, start or stop output queues,
and precise its start date time, its speed of emission, and the data format of the emission.


## Flights

- Create a new flight
- Re-schedule a flight
- Suppress a flight
- Create its handling services during flight creation

## Ground Services

- Create a single service
- Create all services for a given flight (single movement) —— Not implemented yet
- Reschedule an existing service
- Suppress a service

## Missions

- Create a mission
- Reschedule a mission
- Suppress a mission

## Queues

- Create a queue
- Reset a queue
- Start or stop a queue
- Delete a queue


## Airport utility functions

- List all flights
- List all services, service vehicles
- List all missions
- Show allocations for runways, ramps, and service vehicles
- Helper functions to ease use interface building and selection by returning
lists of pairs (internal_name, display_name) for combo boxes and form validation.


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
        "description": "Queue operations: Creating, reset, etc."
    },
    {
        "name": "airport",
        "description": "General airport queries: Allocations, etc."
    }
]

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

if SECURE_API:
    if ALLOW_KEYGEN:
        logger.warning(f":init {emitpy.__version__} «{emitpy.__version_name__}» key generation permitted")
        app.include_router(api_key_router, prefix="/auth", include_in_schema=False)
    dependencies=[Depends(api_key_security)]
else:
    dependencies=[]

logger.info(f":init {emitpy.__version__} «{emitpy.__version_name__}» {'with' if SECURE_API else 'without'} security")

app.include_router(flights.router, dependencies=dependencies)
app.include_router(services.router, dependencies=dependencies)
app.include_router(missions.router, dependencies=dependencies)
app.include_router(airport.router, dependencies=dependencies)

app.include_router(queues.router2, dependencies=dependencies)
app.include_router(queues.router, dependencies=dependencies)

app.mount("/static", StaticFiles(directory="web/static"), name="static")


@app.get("/", tags=["emitpy"], include_in_schema=False)
async def root():
    return fastapi.responses.RedirectResponse(
        "/docs",
        status_code=status.HTTP_302_FOUND)


@app.on_event("startup")
async def startup():
    logger.info(f":startup {emitpy.__version__} «{emitpy.__version_name__}» starting..")
    # should collect and display:
    # git describe --tags
    # git log -1 --format=%cd --relative-date
    # + redis_connect info
    app.state.emitpy = EmitApp(MANAGED_AIRPORT)
    app.state.emitpy.loadFromCache()
    app.state.hypercaster = Hypercaster()
    logger.log(5, f":startup {emitpy.__version__} «{emitpy.__version_name__}» ..started")


@app.on_event("shutdown")
async def shutdown():
    logger.info(f":shutdown {emitpy.__version__} «{emitpy.__version_name__}» ..stopping..")
    app.state.emitpy.saveToCache()
    app.state.hypercaster.shutdown()
    logger.info(f":shutdown {emitpy.__version__} «{emitpy.__version_name__}» ..stopped")




if __name__ == "__main__":
    uvicorn.run("api:app", host="127.0.0.1", port=5000, log_level="info")