# Application constants and global parameters related to the simulation
#
from enum import Enum


class STATS(Enum):
    STARTED = "started"
    FLIGHTS = "flights"
    ARRIVALS = "arrival"
    DEPARTURES = "departure"
    SERVICES = "services"
    ENQUEUED = "enqueued"
    RESCHEDULED = "rescheduled"
    DEQUEUED = "dequeued"
    SENT = "sent"
