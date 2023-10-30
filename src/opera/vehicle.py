import logging
import re

from turf import Feature, LineString, Point, distance

from rule import Event
from aoi import AreasOfInterest

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
        self.stopped = False

        # Rules
        self.events = []  # Rules that apply to this vehicle
        self.messages = []

        self._opera = None

    def ident(self):
        return self._ident

    def set_ident(self, ident):
        self._ident = ident

    def init(self, opera):
        self._opera = opera
        self.events = []
        vmatch = list(filter(lambda f: bool(re.match(f, self.ident())), opera.vehicle_events.keys()))
        logger.debug(f"vehicle has {len(vmatch)} matching rules")
        for r in vmatch:
            self.events = self.events + opera.vehicle_events[r]
        logger.debug(f"vehicle has {len(self.events)} events")
        self._inited = self.ident is not None

    def is_stopped(self):
        STOPPED_DISTANCE_THRESHOLD = 0.005  # 5 meters
        messages = []
        if self.last_position is None:
            return False
        far = distance(self.last_position, self.position)
        print(">>", far)
        return far < STOPPED_DISTANCE_THRESHOLD

    def at(self, position):
        self.last_position = self.position
        self.last_inside = self.inside
        self.position = position
        self.inside = []
        messages = []
        if self.last_position is not None and self.is_stopped():
            msg = Message(event=None, vehicle=self, aoi=None, position=self.position, last_position=None)
            messages.append(msg)
        for event in self.events:
            if event.action in ["enter", "exit", "traverse"]:
                inside = event.inside(position)
                logger.debug(f"{len(inside)} insides")  # we consider it entered all areas it is inside
                self.inside = self.inside + inside
                # first position
                if self.last_position is None:
                    logger.debug(f"first position")  # we consider it entered all areas it is inside
                    if event.action == "enter":
                        for aoi in inside:
                            msg = Message(
                                event=event, vehicle=self, aoi=aoi, position=self.position, last_position=self.last_position
                            )  # note self.last_position = None
                            messages.append(msg)
                            logger.debug(f"added new enter {len(inside)} messages")
                else:
                    match event.action:
                        case "enter":
                            res = list(filter(lambda aoi: aoi not in self.last_inside, inside))
                            logger.debug(f"{len(res)} enters")
                            for aoi in res:
                                msg = Message(event=event, vehicle=self, aoi=aoi, position=self.position, last_position=self.last_position)
                                messages.append(msg)

                        case "exit":
                            res = list(filter(lambda aoi: aoi not in inside, self.last_inside))
                            logger.debug(f"{len(res)} exits")
                            for aoi in res:
                                msg = Message(event=event, vehicle=self, aoi=aoi, position=self.position, last_position=self.last_position)
                                messages.append(msg)

                        case "crossed":
                            line = LineString((self.last_position.geometry.coordinates, self.position.geometry.coordinates))
                            res = event.crossed(line)
                            logger.debug(f"{len(res)} crossed")

                        case "stopped":
                            for aoi in self.inside:
                                msg = Message(event=event, vehicle=self, aoi=aoi, position=self.position, last_position=self.last_position)
                                messages.append(msg)
                            logger.debug(f"{len(self.inside)} stopped")

        self.messages = self.messages + messages
        logger.debug(f"added {len(messages)} messages")
        return messages


class Message:
    """A Message is sent by a vehicle when an event is satisfied"""

    def __init__(self, event: Event, vehicle: Vehicle, aoi: AreasOfInterest, position: Feature, last_position: Feature):
        self.event = event
        self.vehicle = vehicle
        self.aoi = aoi
        self.last_position = last_position
        self.position = position
