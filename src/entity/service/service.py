"""
A Service  is a maintenance operation performed on an aircraft during a turn-around.

"""
import logging
import random
from datetime import datetime

from .servicevehicle import ServiceVehicle
from ..geo import FeatureWithProps

logger = logging.getLogger("Service")


class Service:

    def __init__(self, schedule: int, duration: int):
        self.schedule = schedule  # in minutes
        self.duration = duration  # in minutes
        self.movement = None   # {arrival|departure}
        self.turnaround = None
        self.performer = None
        self.vehicle = None
        self.starttime = None
        self.pos_start = None
        self.pos_end = None
        self.route = []


    def setTurnaround(self, turnaround: 'Turnaround'):
        self.turnaround = turnaround


    def setVehicle(self, vehicle: ServiceVehicle):
        self.vehicle = vehicle


    def setStartPosition(self, position):
        self.pos_start = position


    def setEndPosition(self, position):
        self.pos_end = position


    def make(self, managedAirport):
        if self.vehicle is None:
            logger.warning(":make: %s: no vehicle" % (type(self).__name__))
            return (False, "Service::make no vehicle")

        # find a starting position if none is given
        if self.pos_start is None:
            pss = managedAirport.getServicePOIs(type(self).__name__.replace("Service", ""))
            self.pos_start = random.choice(pss)
            logger.debug(":make: found POI %s, %s" % (self.pos_start.getProp("poi"), self.pos_start.getProp("services")))

        self.route.append(self.pos_start)

        # starting position to network
        np = managedAirport.service_roads.nearest_point_on_edge(self.pos_start)
        self.route.append(np[0])

        start = managedAirport.service_roads.nearest_vertex(self.pos_start)

        # find ramp position, use ramp center if none is given.
        ramp_stop = self.turnaround.ramp.getServicePOI(type(self).__name__.replace("Service", ""))

        # find closest point on network to ramp
        rp = managedAirport.service_roads.nearest_point_on_edge(ramp_stop)
        rv = managedAirport.service_roads.nearest_vertex(ramp_stop)

        # route from start to ramp
        r1 = managedAirport.service_roads.AStar(start[0].id, rv[0].id)

        if r1 is not None:
            for vid in r1:
                vtx = managedAirport.service_roads.get_vertex(vid)
                pos = FeatureWithProps(geometry=vtx["geometry"], properties=vtx["properties"])
                self.route.append(pos)

        self.route.append(rp[0])
        self.route.append(ramp_stop)
        # .. servicing ..

        # find end position if none is given
        if self.pos_end is None:
            pss = managedAirport.getServicePOIs(type(self).__name__.replace("Service", ""))
            if len(pss) > 0:
                self.pos_end = random.choice(pss)


        # find end position on network
        ne = managedAirport.service_roads.nearest_point_on_edge(self.pos_end)
        end = managedAirport.service_roads.nearest_vertex(self.pos_end)

        # route ramp to end position
        self.route.append(rp[0])
        r2 = managedAirport.service_roads.AStar(rv[0].id, end[0].id)
        if r2 is not None:
            for vid in r2:
                vtx = managedAirport.service_roads.get_vertex(vid)
                pos = FeatureWithProps(geometry=vtx["geometry"], properties=vtx["properties"])
                self.route.append(pos)


        self.route.append(ne[0])
        self.route.append(self.pos_end)

        return (False, "Service::make not implemented")


    def run(self, moment: datetime):

        if len(self.route) == 0:
            logger.warning(":run: %s: no movement" % (type(self).__name__))
            return (False, "Service::run no vehicle")


        self.starttime = moment
        return (False, "Service::run not implemented")


class CleaningService(Service):

    def __init__(self, schedule: int, duration: int):
        Service.__init__(self, schedule, duration)


class SewageService(Service):

    def __init__(self, schedule: int, duration: int):
        Service.__init__(self, schedule, duration)


class CateringService(Service):

    def __init__(self, schedule: int, duration: int):
        Service.__init__(self, schedule, duration)


class WaterService(Service):

    def __init__(self, schedule: int, duration: int):
        Service.__init__(self, schedule, duration)


class FuelService(Service):

    def __init__(self, schedule: int, duration: int):
        Service.__init__(self, schedule, duration)


class CargoService(Service):

    def __init__(self, schedule: int, duration: int):
        Service.__init__(self, schedule, duration)


class BaggageService(Service):

    def __init__(self, schedule: int, duration: int):
        Service.__init__(self, schedule, duration)

