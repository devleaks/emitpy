"""
A Service  is a maintenance operation performed on an aircraft during a turn-around.

"""
import logging
import random
from datetime import datetime

from geojson import Feature
from .servicevehicle import ServiceVehicle
from ..geo import FeatureWithProps, printFeatures, asLineString
from ..graph import Route

logger = logging.getLogger("Service")


class Service:

    def __init__(self, schedule: int, duration: int):
        self.schedule = schedule  # scheduled service date/time in minutes after/before(negative) on-block
        self.duration = duration  # scheduled duration in minutes, will be different from actual duration
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
            if self.pos_start is None:
                logger.debug(":make: no start position")
            else:
                logger.debug(":make: found POI %s, %s" % (self.pos_start.getProp("poi"), self.pos_start.getProp("services")))
                self.route.append(self.pos_start)

        # starting position to network
        startnp = managedAirport.service_roads.nearest_point_on_edge(self.pos_start)
        if startnp[0] is None:
            logger.warning(":make: no nearest_point_on_edge for pos_start")
        else:
            self.route.append(startnp[0])

        startnv = managedAirport.service_roads.nearest_vertex(self.pos_start)
        if startnv[0] is None:
            logger.warning(":make: no nearest_vertex for pos_start")

        # find ramp position, use ramp center if none is given.
        ramp_stop = self.turnaround.ramp.getServicePOI(type(self).__name__.replace("Service", ""))

        # find closest point on network to ramp
        rampnp = managedAirport.service_roads.nearest_point_on_edge(ramp_stop)
        if rampnp[0] is None:
            logger.warning(":make: no nearest_point_on_edge for ramp_stop")
        rampnv = managedAirport.service_roads.nearest_vertex(ramp_stop)
        if rampnv[0] is None:
            logger.warning(":make: no nearest_vertex for ramp_stop")

        # route from start to ramp
        logger.debug(":make: route from start %s to ramp %s (vertices)" % (startnv[0].id, rampnv[0].id))
        rt1 = Route(managedAirport.service_roads, startnv[0].id, rampnv[0].id)
        # rt1.find()  # auto route
        # r1 = managedAirport.service_roads.Dijkstra(startnv[0].id, rampnv[0].id)

        if rt1.found():
            for vtx in rt1.get_vertices():
                # vtx = managedAirport.service_roads.get_vertex(vid)
                pos = FeatureWithProps(geometry=vtx["geometry"], properties=vtx["properties"])
                self.route.append(pos)
        else:
            logger.debug(":make: no route from start %s to ramp %s" % (startnv[0].id, rampnv[0].id))

        if rampnp[0] is not None:
            self.route.append(rampnp[0])
        self.route.append(ramp_stop)
        #
        # .. servicing ..
        #
        # find end position if none is given
        if self.pos_end is None:
            pss = managedAirport.getServicePOIs(type(self).__name__.replace("Service", ""))
            if len(pss) > 0:
                self.pos_end = random.choice(pss)
                if self.pos_end is None:
                    logger.debug(":make: no end position")
                    if self.pos_start is not None:
                        self.pos_end = self.pos_start  # if start found send it back there...
                        logger.debug(":make: using start position as end position")
                    else:
                        logger.warning(":make: no end position")
                else:
                    logger.debug(":make: found POI %s, %s" % (self.pos_end.getProp("poi"), self.pos_end.getProp("services")))

                    # find end position on network
                    endnp = managedAirport.service_roads.nearest_point_on_edge(self.pos_end)
                    if endnp[0] is None:
                        logger.warning(":make: no nearest_point_on_edge for end")

                    endnv = managedAirport.service_roads.nearest_vertex(self.pos_end)
                    if endnv[0] is None:
                        logger.warning(":make: no nearest_vertex for end")

                    # route ramp to end position
                    self.route.append(rampnp[0])

                    logger.debug(":make: route from %s to %s" % (rampnv[0].id, endnv[0].id))
                    r2 = managedAirport.service_roads.AStar(rampnv[0].id, endnv[0].id)
                    if r2 is not None:
                        for vid in r2:
                            vtx = managedAirport.service_roads.get_vertex(vid)
                            pos = FeatureWithProps(geometry=vtx["geometry"], properties=vtx["properties"])
                            self.route.append(pos)
                    else:
                        logger.debug(":make: no route from ramp %s to end %s" % (rampnv[0].id, endnv[0].id))

                    if endnp is not None:
                        self.route.append(endnp[0])

                    self.route.append(self.pos_end)


        printFeatures(self.route, "route")
        # printFeatures([Feature(geometry=asLineString(self.route))], "route")

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

