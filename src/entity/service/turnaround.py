"""
A Turnaround is a collection of Services to be performed on an aircraft during a turn-around.

"""
from datetime import datetime

from .service import Service
from ..flight import Flight

class Turnaround:

    def __init__(self, arrival: Flight, departure: Flight):
        self.arrival = arrival
        self.departure = departure
        self.services = []


    def addService(self, service: Service):
        self.services.append(service)


    def plan(self):
        for svc in self.services:
            svc.plan()

        return (False, "Turnaround::plan not implemented")


    def run(self, moment: datetime):
        for svc in self.services:
            svc.run(moment)

        return (False, "Turnaround::plan not implemented")
