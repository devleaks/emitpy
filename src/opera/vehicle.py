import logging
import re

from turf import Feature, LineString, distance

from opera.rule import Event, Promise, Resolve
from opera.aoi import AreasOfInterest

logger = logging.getLogger("vehicle")


class Vehicle:
    """A Vehicle is an object that reports its position at regular interval"""

    def __init__(self, identifier):
        self._inited = False
        self._ident = None
        self._is_aircraft = False
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
        self.archived_promises = []
        self.resolves = []

    def get_id(self):
        """Returns a vehicle identifier"""
        return self._ident

    def set_id(self, ident):
        """Sets a vehicle identifier"""
        self._ident = ident

    def set_aircraft(self, is_aircraft: bool = True):
        """Sets whether the vehicle is identified as an aircraft"""
        self._is_aircraft = is_aircraft

    def is_aircraft(self):
        """Returns whether the vehicle is identified as an aircraft"""
        return self._is_aircraft

    def init(self, opera):
        """Initialize a vehicle

        Initialisation includes pre-selecting all events of interest that this vehicle may produce.

        Args:
            opera ([OperaApp]): Link to main OperaApp container to fetch data from.
        """
        self._opera = opera
        self.events = []
        vmatch = list(filter(lambda f: bool(re.match(f, self.get_id())), opera.vehicle_events.keys()))
        logger.debug(f"vehicle has {len(vmatch)} matching rules")
        for r in vmatch:
            self.events = self.events + opera.vehicle_events[r]
        logger.debug(f"vehicle has {len(self.events)} events")
        self._inited = self._ident is not None

    def is_stopped(self):
        """Determine whether a vehicle is stopped"""
        STOPPED_DISTANCE_THRESHOLD = 0.005  # 5 meters
        messages = []
        if self.last_position is None:
            return False
        far = distance(self.last_position, self.position)
        # logger.debug(far)
        return far < STOPPED_DISTANCE_THRESHOLD

    def promise(self, message):
        """Creates or updates a promise for this vehicle based on the message data

        Args:

            message [[Message]] message emitted by the vehicle when satisfying an Event
        """
        key = Promise.make_id(rule=message.event.rule, vehicle=message.vehicle, aoi=message.aoi)
        if key not in self.promises.keys():
            self.promises[key] = Promise(rule=message.event.rule, vehicle=message.vehicle, aoi=message.aoi, position=message.position, data=message)
            # logger.debug(f"created a promise for rule {message.event.rule.get_id()}, vehicle {message.vehicle.get_id()}, aoi {message.aoi.get_id()}")
        else:
            if self.promises[key].is_expired(message.get_timestamp()):
                self.archive_promise(message=message)
                self.promises[key] = Promise(rule=message.event.rule, vehicle=message.vehicle, aoi=message.aoi, position=message.position, data=message)
                logger.debug(
                    f"archived expired promise, created new promise {message.event.rule.get_id()}, vehicle {message.vehicle.get_id()}, aoi {message.aoi.get_id()}"
                )
            else:
                self.promises[key].reset_timestamp(message.position.get_timestamp())
                logger.debug(
                    f"updated promise timestamp for rule {message.event.rule.get_id()}, vehicle {message.vehicle.get_id()}, aoi {message.aoi.get_id()}"
                )

    def resolve(self, message):
        """Creates a resolve for this vehicle based on the message data

        Args:

            message [[Message]] message emitted by the vehicle when satisfying an Event
        """
        key = Promise.make_id(rule=message.event.rule, vehicle=message.vehicle, aoi=message.aoi)
        if key in self.promises.keys():
            promise = self.promises[key]
            if not promise.is_expired(self.position.get_timestamp()):  # and not promise.resolved()
                resolve = Resolve(promise, message.position, data=message)
                self.resolves.append(resolve)
            else:
                logger.debug(f"promise {promise.rule.get_id()} is expired")

    def archive_promise(self, message):
        key = Promise.make_id(rule=message.event.rule, vehicle=message.vehicle, aoi=message.aoi)
        if key in self.promises.keys():
            self.archived_promises.append(self.promises[key])
            del self.promises[key]

    def process(self, message):
        """Processes a message"""
        if type(message) == StoppedMessage:
            logger.debug(f"stopped message does not need resolution")
            return
        if message.event.is_start():
            self.promise(message)
        else:
            self.resolve(message)

    def at(self, position):
        """Process a position and update the vehicle status

        The procedure first creates a list of messages based on Event satisfied by the position.
        Messages (if any) are then "processed", meaning corresponding promises or resolved are generated or updated.

        Args:
            position ([GeoJSON Feature<Point>]): Last position of vehicle

        Returns:
            list: [description]
        """

        def list_aois(arr):
            return [a.get_id() for a in arr]

        self.last_position = self.position
        self.last_inside = self.inside
        self.position = position
        self.inside = set()
        messages = []

        if self.is_stopped():
            if not self.stopped:
                msg = StoppedMessage(vehicle=self, position=self.position)
                messages.append(msg)
                self.stopped = True  # we only send one message when there is a new stop
            logger.debug(f"{self.get_id()} is stopped {position}")
        else:
            self.stopped = False

        for event in self.events:
            if event.action in ["enter", "exit", "traverse", "stopped"]:
                inside = event.inside(position)
                # logger.debug(f"{len(inside)} insides")  # we consider it entered all areas it is inside
                self.inside = self.inside.union(inside)
                # first position
                if self.last_position is None:
                    logger.debug(
                        f"first position (event {event.rule.get_id()}, {'start' if event.is_start() else 'end'})"
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
        return f"{self.vehicle.identifier}({self.vehicle.get_id()}) rule {self.event.rule.get_id()} {self.event.action} {self.aoi.get_id()}"

    def get_timestamp(self):  # get_precise_timestamp()
        """Compute the exact time of entry of the vehicle in the area."""
        # To do later
        # Make line
        # Find intersection point with curve
        # (if several points, keep first point, closest to last_position)
        # Interpolate time between last_position and position (given speed, etc.)
        return self.position.get_timestamp()


class StoppedMessage(Message):
    """A StopMessage is a special message when a vehicle comes to an halt."""

    def __init__(self, vehicle, position):
        Message.__init__(self, event=None, vehicle=vehicle, aoi=None, position=position, last_position=None)

    def __str__(self):
        return f"{self.vehicle.identifier}({self.vehicle.get_id()}) is stopped"
