from datetime import timedelta
import logging

logger = logging.getLogger("Turnaround")

from .airline import Airline
from .aircraft import AircraftType
from .flight import Flight
from .airport import Parking
from .task import Project, Task, RelatedTask


class Turnaround:
    """
    A Turnaround is a container for all data ans tasks related to turnaround operations of a plane
    between its arrival and its departure to the next destination.
    """
    def __init__(self, arrival: Flight, departure: Flight, parking: Parking, schedule: str):
        self.arrival = arrival
        self.departure = departure
        self.parking = parking
        self.services = []
        self.turnaround = Project("turnaround")  # make name string from flights, parking, schedule

    def mkPlanning(self):
        cargo = Task("cargo", 0)
        self.turnaround.add()

    @staticmethod
    def template(airln: Airline, aplty: AircraftType):
        return timedelta(minutes=90)