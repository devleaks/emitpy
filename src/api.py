import json
import logging

import fastapi
import starlette.status as status

from fastapi import FastAPI, Body, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from web.routers import flights, services, missions, queues, airport

import emitpy
from emitpy.parameters import MANAGED_AIRPORT
from emitpy.emitapp import EmitApp
from emitpy.emit import Hypercaster

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("app")


# #########################@@
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

app.include_router(flights.router)
app.include_router(services.router)
app.include_router(missions.router)
app.include_router(airport.router)

app.include_router(queues.router2)
app.include_router(queues.router)

app.mount("/static", StaticFiles(directory="web/static"), name="static")

@app.get("/", tags=["emitpy"])
async def root():
    return fastapi.responses.RedirectResponse(
        '/docs',
        status_code=status.HTTP_302_FOUND)


@app.on_event("startup")
async def startup():
    logger.info(f"emitpy {emitpy.__version__} «{emitpy.__version_name__}» starting..")
    # should collect and display:
    # git describe --tags
    # git log -1 --format=%cd --relative-date
    # + redis_connect info
    app.state.emitpy = EmitApp(MANAGED_AIRPORT)
    app.state.emitpy.loadFromCache()
    app.state.hypercaster = Hypercaster()
    logger.info(f"emitpy {emitpy.__version__} «{emitpy.__version_name__}» ..started")


@app.on_event("shutdown")
async def shutdown():
    logger.info(f"emitpy {emitpy.__version__} «{emitpy.__version_name__}» ..stopping..")
    app.state.emitpy.saveToCache()
    app.state.hypercaster.terminate_all_queues()
    logger.info(f"emitpy {emitpy.__version__} «{emitpy.__version_name__}» ..stopped")
