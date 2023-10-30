import logging
import re

from turf import Feature, Point

logger = logging.getLogger("vehicle")


class Position(Feature):
    def __init__(self, lat, lon, alt, ts):
        Feature.__init__(self, geom=Point((lon, lat, alt)), properties={"ts": ts})


class Vehicle:
    def __init__(self, identifier):
        self._inited = False
        self._ident = None
        self.identifier = identifier

        # Data relative to positions
        self.last_position = None
        self.position = None
        self.last_inside = {}
        self.inside = {}

        # Rules
        self.events = []  # Rules that apply to this vehicle
        self.generated_events = []

        self._opera = None

    def ident(self):
        return self._ident

    def set_ident(self, ident):
        self._ident = ident

    def init(self, opera):
        self._opera = opera
        vmatch = list(filter(lambda f: re.match(f, self.ident()), opera.vehicle_events.keys()))
        logger.debug(f"vehicle has {len(vmatch)} matching rules")
        for r in vmatch:
            self.events = self.events + opera.vehicle_events[r]
        logger.debug(f"vehicle has {len(self.events)} events")
        self._inited = True

    def at(self, position):
        self.last_position = self.position
        self.position = position
        if self.last_position is None:  # first position
            pass
