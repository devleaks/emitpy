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
    """An Event is something to look for."""

    def __init__(self, aois: [], action: str, vehicles: str = "*", notes: str = None, aoi_selector: str = None):
        self.rule = None
        self._start = False
        self.aoi_selector = aoi_selector  # for information/debug
        self.aois = aois  # Just the aois to check for this rule
        self.action = action  # class Actions
        self.vehicles = vehicles
        self.notes = notes
        self.init()

    def __str__(self):
        return f"rule {self.rule.name} {'start' if self._start else 'end'} {self.vehicles} {self.action} {self.aoi_selector} ({self.notes})"

    def init(self):
        pass

    def set_rule(self, rule):
        self.rule = rule

    def set_start(self, start):
        self._start = start

    def is_start(self) -> bool:
        return self._start

    def inside(self, position) -> list:
        return list(filter(lambda aoi: point_in_polygon(position, aoi), self.aois))

    def crossed(self, line) -> list:
        # Note: line_intersect_polygon returns the number of points of intersection
        # To intersect, there must be at least a point of intersection (tangent) or more points.
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
        self._resolved = False
        self.start.set_rule(self)
        self.start.set_start(True)
        self.end.set_rule(self)

    def __str__(self):
        return " ".join(
            [
                f"Rule {self.name}",
                f"{self.start.vehicles} {self.start.action} {self.start.aoi_selector}",
                f"{self.start.vehicles} {self.start.action} {self.start.aoi_selector}",
                f"({self.notes})",
            ]
        )


class Promise:
    """A Promise is a Rule that has its start condition satisfied

    [description]
    """

    def __init__(self, rule: Rule, vehicle: "Vehicle", position, data):
        self.rule = rule
        self.vehicle = vehicle
        self.position = position
        self.data = data

        self.ts = position.get_timestamp()

    def get_timestamp(self):
        """Returns precise timestamp of message, i.e. when vehicle interacted with aoi and initiated this promise"""
        return self.data.get_timestamp()

    def reset_timestamp(self, ts):
        self.ts = ts

    def is_expired(self, ts):
        ret = (self.ts + self.rule.timeout) < ts
        if ret:
            logger.debug(f"promise {self.rule.name} is expired: {self.ts} + {self.rule.timeout} = {self.ts + self.rule.timeout} < {ts}")
        return (self.ts + self.rule.timeout) < ts

    def resolved(self):
        """Set if resolved at least once"""
        self._resolved = True

    def is_resolved(self, position):
        return self._resolved


class Resolve:
    """A Resolve is a Rule that has its start and end conditions satisfied.

    [description]
    """

    def __init__(self, promise: Promise, position, data):
        self.promise = promise
        self.position = position
        self.data = data
        self.ts = position.get_timestamp()
        logger.debug(self)

    def __str__(self):
        rule = self.promise.rule
        # return " ".join(
        #     [
        #         f"Resolve rule {rule.name}",
        #         f"{rule.start.vehicles} {rule.start.action} {rule.start.aoi_selector}",
        #         f"with {self.promise.vehicle.get_id()} {self.promise.data.aoi.get_id()}",
        #         f"{rule.end.vehicles} {rule.end.action} {rule.end.aoi_selector}",
        #         f"with {self.data.aoi.get_id()}",
        #         f"(reason {rule.notes})",
        #     ]
        # )
        return " ".join(
            [
                f"Resolve rule {rule.name} with {self.promise.vehicle.get_id()}",
                f"{rule.start.action} {self.promise.data.aoi.get_id()} at {round(self.promise.get_timestamp(), 1)}",
                f"{rule.end.action} {self.data.aoi.get_id()}",  #  at {self.get_timestamp()}
                f"duration {round(self.get_timestamp()-self.promise.get_timestamp())}s (reason {rule.notes})",
            ]
        )

    def get_timestamp(self):
        """Returns precise timestamp of message, i.e. when vehicle interacted with aoi and initiated this resolve"""
        return self.data.get_timestamp()

    def analyze(self) -> dict:
        # what gets saved for further analysis
        rule = self.promise.rule
        return {"rule": rule.name, "note": rule.notes, "vehicle": self.promise.vehicle.get_id()}
