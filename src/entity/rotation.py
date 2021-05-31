from datetime import timedelta
import logging

logger = logging.getLogger("Rotation")

from .airline import Airline
from .aircraft import AircraftType
from .flight import Flight
from .airport import Parking


class Rotation:
    """
    A Rotation is a container for all data ans tasks related to a rotation of a plane
    """
    def __init__(self, arrival: Flight, departure: Flight, parking: Parking, schedule: str):
        self.service = service

    @staticmethod
    def template(airln: Airline, aplty: AircraftType):
        return timedelta(minutes=90)