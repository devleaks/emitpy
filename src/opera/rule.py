import logging
import csv
import json
import re
from emitpy.geo.turf import point_in_polygon

logger = logging.getLogger("rule")


class Event:
    """An Event is something to look for

    [description]
    """

    def __init__(self, aois: [], action: str, vehicles: str = "*", notes: str = None):
        self.aois = aois
        self.action = action
        self.vehicles = vehicles
        self.notes = notes

    def init(self):
        pass

    def match(self, position, last_position) -> bool:
        aircraft = position.getPropPath("$.flight.aircraft.identity")
        if re.match(self.vehicles, aircraft):
            m = filter(lambda x: point_in_polygon(position, x), self.aois)
            r = len(list(m))
            print(f"match: {r}")
            return r > 0
        print(f"not a valid vehicle")
        return False


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
