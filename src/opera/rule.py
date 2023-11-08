import logging
import csv
import json
import re
from enum import Enum
from emitpy.constants import ID_SEP

from emitpy.geo.turf import EmitpyFeature, point_in_polygon, line_intersect_polygon

logger = logging.getLogger("rule")


class Actions(Enum):
    """List of valid actions for an Event"""

    ENTER = "enter"
    EXIT = "exit"
    TRAVERSE = "traverse"
    STOPPED = "stopped"


class Event:
    """An Event is something to look for."""

    def __init__(self, aois: [], action: str, vehicles: str = "*", notes: str = None, aoi_selector: str = None):
        self.rule = None
        self._start = False
        self._enabled = True
        self.aoi_selector = aoi_selector  # for information/debug
        self.aois = aois  # Just the aois to check for this rule
        self.action = action  # class Actions
        self.vehicles = vehicles
        self.notes = notes
        self.init()

    def __str__(self):
        """Print string for an Event, mainly used for debugging"""
        return f"rule {self.rule.get_id()} {'start' if self._start else 'end'} {self.vehicles} {self.action} {self.aoi_selector} ({self.notes})"

    def init(self):
        pass

    def set_rule(self, rule):
        """Sets the rule the event belongs to"""
        self.rule = rule

    def set_start(self, start):
        """Sets whether the event is a start event of a Rule"""
        self._start = start

    def is_start(self) -> bool:
        """Returns whether the event is a start event of a Rule"""
        return self.rule is not None and self._start

    def inside(self, position) -> set:
        """Returns a set of areas of interest where the position resides.
        Args:
            position ([GeoJSON Feature<Point>]): Position to test against the Event AoIs.

        Returns:
            set: set of areas of interest where the position resides
        """
        return set(filter(lambda aoi: point_in_polygon(position, aoi), self.aois))

    def crossed(self, line) -> set:
        """Returns a set of areas of interest that the line touches or crosses.
        Args:
            line ([GeoJSON Feature<LineString>]): Line normally joining 2 positions.

        Returns:
            set: set of areas of interest that the line touches or crosses
        """
        # Note: line_intersect_polygon returns the number of points of intersection
        # To intersect, there must be at least a point of intersection (tangent) or more points.
        return set(filter(lambda aoi: line_intersect_polygon(line=line, polygon=aoi) > 0, self.aois))


class Rule:
    """A Rule is a pair of matching events

    [description]
    """

    def __init__(self, start: Event, end: Event, timeout: float, name: str, notes: str = None):
        self._enabled = True
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
        """Print string for a Rule, mainly used for debugging"""
        return " ".join(
            [
                f"Rule {self.name}",
                f"{self.start.vehicles} {self.start.action} {self.start.aoi_selector}",
                f"{self.start.vehicles} {self.start.action} {self.start.aoi_selector}",
                f"({self.notes})",
            ]
        )

    def get_id(self):
        """Returns the name or identifier of the rule.
        Returns:
            [str]: name or identifier of the rule
        """
        return str(self.name)


class Promise:
    """A Promise is a Rule that has its start condition satisfied

    [description]
    """

    def __init__(self, rule: Rule, vehicle: "Vehicle", aoi: EmitpyFeature, position, data):
        self.rule = rule
        self.vehicle = vehicle
        self.position = position
        self.aoi = aoi
        self.data = data

        self.ts = position.get_timestamp()

        self._ident = ID_SEP.join([self.rule.get_id()] + vehicle.get_id().split(ID_SEP) + aoi.get_id().split(ID_SEP))

        logger.debug(self)

    def __str__(self):
        """Print string for a Promise, mainly used for debugging"""
        rule = self.rule
        return " ".join(
            [f"Promise rule {rule.get_id()} with {self.vehicle.get_id()}", f"{rule.start.action} {self.data.aoi.get_id()} at {round(self.get_timestamp(), 1)}"]
        )

    @staticmethod
    def make_id(rule, vehicle, aoi):
        """Creates a unique identifier for a Promise, based on a rule, a vehicle and an area of interest.

        Args:
            rule ([type]): [description]
            vehicle ([type]): [description]
            aoi ([type]): [description]

        Returns:
            [str]: unique identifier for a Promise
        """
        return ID_SEP.join([rule.get_id()] + vehicle.get_id().split(ID_SEP) + aoi.get_id().split(ID_SEP))

    def get_timestamp(self):
        """Returns precise timestamp of message, i.e. when vehicle interacted with aoi and initiated this promise"""
        return self.data.get_timestamp()

    def get_id(self):
        """Returns identifier of a promise"""
        return self._ident

    def reset_timestamp(self, ts):
        """Reset the creation timestamp of a promise

        When a now occurence of the same event arrives, the promise timeout is reset.

        Args:
            ts ([timestamp]): Timestamp of more recent occurence of the event, placed in the promise to evaluate a new expiration date time.
        """
        logger.debug(f"updated promise for rule {self.rule.get_id()} for vehicle {self.vehicle.get_id()}")
        self.ts = ts

    def is_expired(self, ts):
        """Determine if the Promise is expired or not.

        [description]

        Args:
            ts ([type]): [description]

        Returns:
            tuple: [description]
        """
        ret = (self.ts + self.rule.timeout) < ts
        if ret:
            logger.debug(f"promise {self.rule.get_id()} is expired: {self.ts} + {self.rule.timeout} = {self.ts + self.rule.timeout} < {ts}")
        return (self.ts + self.rule.timeout) < ts

    def resolved(self):
        """Set if Promise is resolved at least once"""
        self._resolved = True

    def is_resolved(self, position):
        """Returns whether promise has been resolved at least once."""
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

        self._ident = Promise.make_id(rule=data.event.rule, vehicle=data.vehicle, aoi=data.aoi)

        self.promise.resolved()

        logger.debug(self)

    def __str__(self):
        """Print string for a Resolve, mainly used for debugging"""
        rule = self.promise.rule
        return " ".join(
            [
                f"Resolve rule {rule.get_id()} with {self.promise.vehicle.get_id()}",
                f"{rule.start.action} {self.promise.data.aoi.get_id()} at {round(self.promise.get_timestamp(), 1)}",
                f"{rule.end.action} {self.data.aoi.get_id()}",  #  at {self.get_timestamp()}
                f"duration {round(self.get_timestamp()-self.promise.get_timestamp())}s (reason {rule.notes})",
            ]
        )

    def get_id(self):
        """Returns identifier of the resolution of the promise, based on the data of the end event.
        Returns:
            [str]: identifier of the resolution of a promise
        """
        return self._ident

    def get_timestamp(self):
        """Returns precise timestamp of message, i.e. when vehicle interacted with aoi and initiated this resolve"""
        return self.data.get_timestamp()

    def analyze(self) -> dict:
        """Returns a dictionary of values to remember for this Resolve

        [description]

        Returns:
            dict: values to remember for this Resolve
        """
        rule = self.promise.rule
        return {"rule": rule.get_id(), "note": rule.notes, "vehicle": self.promise.vehicle.get_id()}
