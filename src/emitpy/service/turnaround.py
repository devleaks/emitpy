"""
A Turnaround is a collection of Services to be performed on an aircraft during a turn-around.

"""
import logging

from ..flight import Flight
from ..service import ServiceFlight

logger = logging.getLogger("Turnaround")


class Turnaround:

    def __init__(self, arrival: Flight, departure: Flight, operator: "Company"):
        arrival.setLinkedFlight(departure)
        self.arrival = ServiceFlight(arrival, operator)
        self.departure = ServiceFlight(departure, operator)
        self.airport = None

    def setManagedAirport(self, airport):
        self.airport = airport
        self.arrival.setManagedAirport(airport)
        self.departure.setManagedAirport(airport)

    def service(self):
        self.arrival.service()
        self.departure.service()

    def move(self):
        self.arrival.move()
        self.departure.move()

    def emit(self, emit_rate: int):
        self.arrival.emit(emit_rate)
        self.departure.emit(emit_rate)

    def saveDB(self):
        self.arrival.saveDB()
        self.departure.saveDB()
