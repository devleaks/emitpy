import json
import logging
from fastapi import FastAPI, Body, File
from fastapi.middleware.cors import CORSMiddleware

from datetime import datetime, date, time, timedelta
from typing import Optional, Literal, List

from pydantic import BaseModel, Field, validator

from emitpy.constants import ARRIVAL, DEPARTURE, EMIT_RATES

from web.routers import flights, services, missions, queues, airport

import emitpy
from emitpy.parameters import MANAGED_AIRPORT
from emitpy.emitapp import EmitApp
from emitpy.emit import RedisUtils

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

The generator also allows you to control output queues (create, re-schedule, restart...)


## Flights


## Ground Services

You will be able to:

* **Create services** (_not implemented_).
* **Re-schedule services** (_not implemented_).


## Missions


## Queues


## Utility functions


(more blabla to come here soon. Trust me.)
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
]

# git describe --tags
# git log -1 --format=%cd --relative-date
# + redis_connect info
emitpyapp = EmitApp(MANAGED_AIRPORT)

logger.info(f"emitpy {emitpy.__version__} «{emitpy.__version_name__}» starting..")


app = FastAPI(
    title="Emitpy REST API",
    description=description,
    version="0.1.0",
    license_info={
        "name": "MIT",
        "url": "https://mit-license.org",
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
app.include_router(queues.router)
app.include_router(airport.router)


@app.get("/")
async def root():
    return {
        "status": 1,
        "message": "emitpy REST API listening...",
        "data": "version 0.5.2"
    }