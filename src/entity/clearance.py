from datetime import datetime
import logging

logger = logging.getLogger("Clearance")


from .resource import Resource
from .airport.runway import Runway


class Availability:
    """
    Container for availability
    """
    def __init__(self, name, moment, slot):
        self.name = name
        self.moment = moment
        self.slot = slot
        self.reservation = None


class Clearance:
    """
    Manages runway assignment for arrival and departure
    """

    def __init__(self, runways: [Runway], slot: int):
        self.runways = runways
        self.slot = slot
        self.rwyrsrcs = {}

        for r in self.runways.keys():
            self.rwyrsrcs[r] = Resource(r, self.slot)
        logger.debug("inited")


    def available_slots(self, moment: datetime, move: str, payload: str):
        avail = []
        for rwy in self.runways.values():
            slots = []
            if move is None or rwy.use(move):
                if payload is None or rwy.use(payload):
                    slots = self.rwyrsrcs[rwy.name].calendar.get_available_slots(moment)
            for s in slots:
                avail.append(Availability(name=rwy.name, moment=moment, slot=s))

        return avail


    def book(self, availability: Availability):
        return self.rwyrsrcs[availability.name].calendar.book(availability.name, availability.moment, availability.slot)


    def time(self, availability: Availability):
        return self.rwyrsrcs[availability.name].calendar.get_slot_time(availability.moment, availability.slot)