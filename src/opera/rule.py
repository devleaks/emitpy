import logging
import csv
import json
import re
from enum import Enum

from emitpy.geo.turf import point_in_polygon, line_intersect_polygon

logger = logging.getLogger("rule")


class Actions(Enum):
    ENTER = "enter"
    EXIT = "exit"
    TRAVERSE = "traverse"
    STOPPED = "stopped"


class Event:
    """An Event is something to look for

    [description]
    """

    def __init__(self, aois: [], action: str, vehicles: str = "*", notes: str = None):
        self._rule = None
        self._start = False
        self.aois = aois
        self.action = action
        self.vehicles = vehicles
        self.notes = notes

    def init(self):
        pass

    def set_rule(self, rule):
        self._rule = rule

    def set_start(self, start):
        self._start = start

    def is_start(self) -> bool:
        return self._start

    def inside(self, position) -> list:
        return list(filter(lambda aoi: point_in_polygon(position, aoi), self.aois))

    def crossed(self, line) -> list:
        # Note: line_intersect_polygon returns the number of points of intersection
        return list(filter(lambda aoi: line_intersect_polygon(line=line, polygon=aoi) > 0, self.aois))


class Rule:
    """A Rule is a pair of matching events

    [description]
    """

    def __init__(self, start: Event, end: Event, timeout: float, name: str, notes: str = None):
        self.start = start
        self.end = end
        self.timeout = timeout
        self.name = name
        self.notes = notes
        self.start.set_rule(self)
        self.start.set_start(True)
        self.end.set_rule(self)

    def promise(self, position, last_position):
        if self.start.match(position, last_position):
            return Promise(rule=self, position=position)
        return None


class Promise:
    """A Promise is a Rule that has its start condition satisfied

    [description]
    """

    def __init__(self, rule: Rule, position: dict):
        self.rule = rule
        self.position = position

        self.ts = position.getAbsoluteEmissionTime()

    def resolve(self, position):
        if self.rule.end.match(position):
            return Resolve(promise=self, position=position)
        return None


class Resolve:
    """A Resolve is a Rule that has its start and end conditions satisfied.

    [description]
    """

    def __init__(self, promise: Promise, position: dict):
        self.promise = promise
        self.position = position
        self.ts = position.getAbsoluteEmissionTime()

    def analyze(self) -> dict:
        # what gets saved for further analysis
        return {}
