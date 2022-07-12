"""
A Turnaround is a collection of Services to be performed on an aircraft during a turn-around.

"""
import logging

from emitpy.flight import Flight
from emitpy.service import FlightServices

logger = logging.getLogger("Turnaround")


class Turnaround:
    """
    Convenience wrapper around a pair of linked, related flight.
    Calls FlightServices on a pair of flights.
    """

    def __init__(self, arrival: Flight, departure: Flight, operator: "Company"):
        arrival.setLinkedFlight(departure)
        self.arrival = FlightServices(arrival, operator)
        self.departure = FlightServices(departure, operator)
        self.airport = None
        self.arrival.setLinkedFlight(linked_flight=self.departure)  # will do the reverse as well
        if self.towed():
            logger.warning(":init: aircraft towed between linked flights")

    def towed(self):
        return self.arrival.ramp != self.departure.ramp

    def setManagedAirport(self, airport):
        self.airport = airport
        self.arrival.setManagedAirport(airport)
        self.departure.setManagedAirport(airport)

    def service(self):
        # If towed, should schedule towing
        self.arrival.service()
        self.departure.service()

    def move(self):
        self.arrival.move()
        self.departure.move()

    def emit(self, emit_rate: int):
        self.arrival.emit(emit_rate)
        self.departure.emit(emit_rate)

    def save(self, redis):
        self.arrival.save(redis)
        self.departure.save(redis)
