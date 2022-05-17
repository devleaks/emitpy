"""
EmitMeta class contains essential information about the movements that resulted in emission of position of point.
Instances are built from {flight,service,mission} move/emit meta data saved in Redis.
From these meta-data + (unformatted) emit positions it is possible to recreate formatted
position to be enqueued. It should only be constructed from simple, JSON friendly data (string, number, boolean, dict
of former).

Somehow, with luck and careful processing, it is even possible to start from the movement
and create a new emission, with, for instance, new broadcast frequency.

On the side, it also is a test of Redis-om.

"""
import os
import json
import flatdict
import logging

from abc import ABC
from datetime import datetime, timedelta
from typing import Mapping

from typing import Optional, Union, List
from collections import namedtuple
from pydantic import Field

from redis.commands.json.path import Path

from redis_om import (
    EmbeddedJsonModel,
    JsonModel,
    Field,
    Migrator,
    get_redis_connection
)

from emitpy.geo import Movement
from emitpy.utils import key_path

from emitpy.constants import REDIS_DATABASE, ID_SEP
from emitpy.parameters import AODB_DIR, REDIS_CONNECT

logger = logging.getLogger("EmitMeta")

redis = get_redis_connection()


class MovementMeta(EmbeddedJsonModel, ABC):
    move_id: str = Field(index=True)

    scheduled: datetime
    estimated: datetime
    actual: datetime
    last_updated: datetime

    esthist: List[ namedtuple("EstimateHistory", ["est", "when", "who", "why"]) ]

    class Meta:
        database: redis
        global_key_prefix: REDIS_DATABASE.EMIT_METAS.value + ID_SEP
        embedded: True


class GroundSupportMeta(MovementMeta, ABC):
    actual_end: datetime
    vehicle_model: Optional[str]


class FlightMeta(MovementMeta):
    flight_id: str = Field(index=True)
    linked_flight_id: Optional[str]
    is_arrival: bool
    airport_icao: str
    ac_type: str
    ac_reg: str
    ramp: str

    class Meta:
        model_key_prefix: REDIS_DATABASE.FLIGHTS.value + ID_SEP


class ServiceMeta(GroundSupportMeta):
    service_type: str
    quantity: float
    ramp: str

    class Meta:
        model_key_prefix: REDIS_DATABASE.SERVICES.value + ID_SEP


class MissionMeta(GroundSupportMeta):
    mission_type: str
    checkpoints: List[str]

    class Meta:
        model_key_prefix: REDIS_DATABASE.MISSIONS.value + ID_SEP


class EmitMeta(JsonModel):
    """
    Composed from above base models
    """
    move_meta: Union[FlightMeta, ServiceMeta, MissionMeta]
    emit_id: str = Field(index=True)
    frequency: float
    formatter: str
    queue: str

