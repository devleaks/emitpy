import logging
import re

from turf import Feature, LineString, distance

from opera.rule import Event, Promise, Resolve
from opera.aoi import AreasOfInterest

logger = logging.getLogger("vehicle")


# class TimedPosition(Feature):
#     def __init__(self, lat, lon, alt, ts):
#         Feature.__init__(self, geom=Point((lon, lat, alt)), properties={"ts": ts})


class Vehicle:
    def __init__(self, identifier):
        self._inited = False
        self._ident = None
        self.identifier = identifier

        self._opera = None

        # Data relative to positions
        self.last_position = None
        self.position = None
        self.last_inside = set()
        self.inside = set()
        self.stopped = False

        # Events
        self.events = []  # Rules that apply to this vehicle
        self.messages = []

        # Rules
        self.promises = {}
        self.resolves = []

    def get_id(self):
        return self._ident

    def set_id(self, ident):
        self._ident = ident

    def init(self, opera):
        self._opera = opera
        self.events = []
        vmatch = list(filter(lambda f: bool(re.match(f, self.get_id())), opera.vehicle_events.keys()))
        logger.debug(f"vehicle has {len(vmatch)} matching rules")
        for r in vmatch:
            self.events = self.events + opera.vehicle_events[r]
        logger.debug(f"vehicle has {len(self.events)} events")
        self._inited = self._ident is not None

    def is_stopped(self):
        STOPPED_DISTANCE_THRESHOLD = 0.005  # 5 meters
        messages = []
        if self.last_position is None:
            return False
        far = distance(self.last_position, self.position)
        # logger.debug(far)
        return far < STOPPED_DISTANCE_THRESHOLD

    def promise(self, message):
        key = message.event.rule.name
        if key not in self.promises.keys():
            self.promises[key] = Promise(rule=message.event.rule, vehicle=message.vehicle, position=message.position, data=message)
            # logger.debug(f"created a promise for rule {key} for vehicle {message.vehicle.get_id()}")
        else:
            self.promises[key].reset_timestamp(message.position.get_timestamp())
            logger.debug(f"updated promise for rule {key} for vehicle {message.vehicle.get_id()}")

    def resolve(self, message):
        # we have an end-event for all these promises
        promises = filter(lambda p: p.rule.name == message.event.rule.name, self.promises.values())
        for p in promises:
            if not p.is_expired(self.position.get_timestamp()):
                resolve = Resolve(p, message.position, data=message)
                p.resolved()
                self.resolves.append(resolve)
                # logger.debug(f"resolved {p.rule.name} for vehicle {self.get_id()}")
            else:
                logger.debug(f"promise {p.rule.name} is expired")

    def process(self, message):
        if type(message) == StoppedMessage:
            logger.debug(f"stopped message does not need resolution")
            return
        if message.event.is_start():
            self.promise(message)
        else:
            self.resolve(message)

    def at(self, position):
        def list_aois(arr):
            return [a.get_id() for a in arr]

        self.last_position = self.position
        self.last_inside = self.inside
        self.position = position
        self.inside = set()
        messages = []

        if self.last_position is not None and self.is_stopped():
            msg = StoppedMessage(vehicle=self, position=self.position)
            messages.append(msg)
            logger.debug(f"{self.get_id()} stopped")

        for event in self.events:
            if event.action in ["enter", "exit", "traverse"]:
                inside = event.inside(position)
                # logger.debug(f"{len(inside)} insides")  # we consider it entered all areas it is inside
                self.inside = self.inside.union(inside)
                # first position
                if self.last_position is None:
                    logger.debug(
                        f"first position (event {event.rule.name}, {'start' if event.is_start() else 'end'})"
                    )  # we consider it entered all areas it is inside
                    if event.action == "enter":
                        for aoi in inside:
                            msg = Message(
                                event=event, vehicle=self, aoi=aoi, position=self.position, last_position=self.last_position
                            )  # note self.last_position = None
                            messages.append(msg)
                        # logger.debug(f"added new enter {len(inside)} messages")
                else:
                    match event.action:
                        case "enter":
                            res = set(filter(lambda aoi: aoi not in self.last_inside, inside))
                            # logger.debug(f"{len(res)} enters ({list_aois(self.last_inside)}/{list_aois(inside)})")
                            for aoi in res:
                                msg = Message(event=event, vehicle=self, aoi=aoi, position=self.position, last_position=self.last_position)
                                messages.append(msg)

                        case "exit":
                            res = set(filter(lambda aoi: (aoi in event.aois) and (aoi not in inside), self.last_inside))
                            # logger.debug(f"{len(res)} exits")
                            for aoi in res:
                                msg = Message(event=event, vehicle=self, aoi=aoi, position=self.position, last_position=self.last_position)
                                messages.append(msg)

                        case "crossed":
                            line = LineString((self.last_position.geometry.coordinates, self.position.geometry.coordinates))
                            res = event.crossed(line)
                            # logger.debug(f"{len(res)} crossed")

                        case "stopped":
                            if self.is_stopped():
                                for aoi in self.inside:
                                    msg = Message(event=event, vehicle=self, aoi=aoi, position=self.position, last_position=self.last_position)
                                    messages.append(msg)
                                # logger.debug(f"{len(self.inside)} stopped inside aoi")

        logger.debug(f"added {len(messages)} messages")
        self.messages = self.messages + messages

        # 2. Check for promise/resolve
        for message in messages:
            self.process(message)


class Message:
    """A Message is sent by a vehicle when an event is satisfied"""

    def __init__(self, event: Event, vehicle: Vehicle, aoi: AreasOfInterest, position: Feature, last_position: Feature):
        self.event = event
        self.vehicle = vehicle
        self.aoi = aoi
        self.last_position = last_position
        self.position = position
        logger.debug(self)

    def __str__(self):
        return f"{self.vehicle.identifier}({self.vehicle.get_id()}) rule {self.event.rule.name} {self.event.action} {self.aoi.get_id()}"

    def get_timestamp(self):  # get_precise_timestamp()
        """Compute the exact time of entry of the vehicle in the area."""
        # To do later
        # Make line
        # Find intersection point with curve
        # (if several points, keep first point, closest to last_position)
        # Interpolate time between last_position and position (given speed, etc.)
        return self.position.get_timestamp()


class StoppedMessage(Message):
    def __init__(self, vehicle, position):
        Message.__init__(self, event=None, vehicle=vehicle, aoi=None, position=position, last_position=None)

    def __str__(self):
        return f"{self.vehicle.identifier}({self.vehicle.get_id()}) is stopped"
