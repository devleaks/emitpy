"""
Build movement of a service vehicle
"""
import os
import json
import logging
from math import pi
import copy

from geojson import Point, LineString, FeatureCollection, Feature
from turfpy.measurement import distance, destination, bearing

from ..airport import AirportBase
from ..geo import MovePoint, Movement, FeatureWithProps, printFeatures
from ..service import Service, ServiceVehicle
from ..graph import Route

logger = logging.getLogger("ServiceMove")


class ServiceMove(Movement):
    """
    Movement build the detailed path of the aircraft, both on the ground (taxi) and in the air,
    from takeoff to landing and roll out.
    """
    def __init__(self, service: Service, airport: AirportBase):
        Movement.__init__(self, airport=airport)
        self.service = service


    def load(self):
        pass


    def save(self):
        pass


    def move(self):
        startpos = self.service.vehicle.getPosition()
        logger.debug(":move: start position %s" % (startpos))
        service_type = type(self.service).__name__.replace("Service", "")

        # starting position to network
        startnp = self.airport.service_roads.nearest_point_on_edge(startpos)
        if startnp[0] is None:
            logger.warning(":move: no nearest_point_on_edge for startpos")
        else:
            self.moves.append(startnp[0])

        logger.debug(":move: start vertex %s" % (startnp[0]))

        startnv = self.airport.service_roads.nearest_vertex(startpos)
        if startnv[0] is None:
            logger.warning(":move: no nearest_vertex for startpos")

        # find ramp position, use ramp center if none is given
        ramp_stop = self.service.ramp.getServicePOI(service_type)

        if ramp_stop is None:
            logger.warning(f":move: failed to find ramp stop for { service_type }, using ramp center")
            ramp_stop = self.service.ramp  # use center of ramp

        if ramp_stop is None:
            logger.warning(f":move: failed to find ramp stop and/or center for { service_type }")
            return (False, ":move: failed to find ramp stop")

        logger.debug(":move: ramp %s" % (ramp_stop))

        # find closest point on network to ramp
        rampnp = self.airport.service_roads.nearest_point_on_edge(ramp_stop)
        if rampnp[0] is None:
            logger.warning(":move: no nearest_point_on_edge for ramp_stop")
        rampnv = self.airport.service_roads.nearest_vertex(ramp_stop)
        if rampnv[0] is None:
            logger.warning(":move: no nearest_vertex for ramp_stop")

        logger.debug(":move: ramp vertex %s" % (rampnv[0]))

        # route from start to ramp
        logger.debug(":move: route from start %s to ramp %s (vertices)" % (startnv[0].id, rampnv[0].id))
        rt1 = Route(self.airport.service_roads, startnv[0].id, rampnv[0].id)
        # rt1.find()  # auto route
        # r1 = self.airport.service_roads.Dijkstra(startnv[0].id, rampnv[0].id)

        if rt1.found():
            for vtx in rt1.get_vertices():
                # vtx = self.airport.service_roads.get_vertex(vid)
                pos = FeatureWithProps(geometry=vtx["geometry"], properties=vtx["properties"])
                pos.setProp("_serviceroad", vtx.id)
                self.moves.append(pos)
        else:
            logger.debug(":move: no route from start %s to ramp %s" % (startnv[0].id, rampnv[0].id))

        if rampnp[0] is not None:
            self.moves.append(rampnp[0])
        self.moves.append(ramp_stop)

        self.service.vehicle.setPosition(ramp_stop)

        # .. servicing ..
        # before service, may first go to ramp rest area.
        # after service, may first go to ramp rest area before leaving ramp.
        #
        # find end position if none is given

        finalpos = self.service.next_position
        if finalpos is None:
            finalpos = self.airport.selectRandomServiceRestArea(service_type)
            # logger.debug(f":move: end position { finalpos }")

            if finalpos is None:
                logger.warning(f":move: no end rest area for { service_type }, using start position")
                finalpos = startpos


        # find end position on network
        endnp = self.airport.service_roads.nearest_point_on_edge(finalpos)
        if endnp[0] is None:
            logger.warning(":move: no nearest_point_on_edge for end")

        endnv = self.airport.service_roads.nearest_vertex(finalpos)
        if endnv[0] is None:
            logger.warning(":move: no nearest_vertex for end")

        # route ramp to end position
        self.moves.append(rampnp[0])

        logger.debug(":move: route from %s to %s" % (rampnv[0].id, endnv[0].id))
        r2 = Route(self.airport.service_roads, rampnv[0].id, endnv[0].id)
        if r2.found():
            for vtx in r2.get_vertices():
                pos = FeatureWithProps(geometry=vtx["geometry"], properties=vtx["properties"])
                pos.setProp("_serviceroad", vtx.id)
                self.moves.append(pos)
        else:
            logger.debug(":move: no route from ramp %s to end %s" % (rampnv[0].id, endnv[0].id))

        if endnp is not None:
            self.moves.append(endnp[0])

        self.moves.append(finalpos)
        self.service.vehicle.setPosition(finalpos)


        printFeatures(self.moves, "route")
        # printFeatures([Feature(geometry=asLineString(self.moves))], "route")

        return (False, "Service::make not implemented")


