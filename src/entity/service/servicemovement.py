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
from ..geo import MovePoint, Movement, FeatureWithProps, printFeatures, asLineString
from ..service import Service, ServiceVehicle
from ..graph import Route
from ..utils import compute_time as doTime
from ..constants import FEATPROP, SERVICE_PHASE

logger = logging.getLogger("ServiceMove")


class ServiceMove(Movement):
    """
    Movement build the detailed path of the aircraft, both on the ground (taxi) and in the air,
    from takeoff to landing and roll out.
    """
    def __init__(self, service: Service, airport: AirportBase):
        Movement.__init__(self, airport=airport)
        self.service = service


    def getId(self):
        return self.service.getId()


    def getInfo(self):
        return self.service.getInfo()


    def move(self):
        speeds = self.service.vehicle.speed

        startpos = self.service.vehicle.getPosition()
        # logger.debug(":move: start position %s" % (startpos))
        service_type = type(self.service).__name__.replace("Service", "").lower()

        startpos.setSpeed(0)  # starts at rest
        startpos.setProp(FEATPROP.MARK.value, SERVICE_PHASE.START.value)
        self.moves.append(startpos)

        # starting position to network
        startnp = self.airport.service_roads.nearest_point_on_edge(startpos)
        if startnp[0] is None:
            logger.warning(":move: no nearest_point_on_edge for startpos")
        else:
            startnp[0].setSpeed(speeds["slow"])  # starts moving
            self.moves.append(startnp[0])

        # logger.debug(":move: start vertex %s" % (startnp[0]))

        startnv = self.airport.service_roads.nearest_vertex(startpos)
        if startnv[0] is None:
            logger.warning(":move: no nearest_vertex for startpos")

        # find ramp position, use ramp center if none is given
        gseraw = self.service.flight.aircraft.actype.gseraw
        if gseraw is not None:
            status = self.service.ramp.makeServicePOIs(gseraw)
            if not status[0]:
                logger.warning(f":move:create ramp service points failed {gseraw}")
            else:
                logger.debug(f':move:created ramp service points {list(gseraw["services"].keys())}')

        ramp_stop = self.service.ramp.getServicePOI(service_type)

        if ramp_stop is None:
            logger.warning(f":move: failed to find ramp stop for { service_type }, using ramp center")
            ramp_stop = self.service.ramp  # use center of ramp

        if ramp_stop is None:
            logger.warning(f":move: failed to find ramp stop and/or center for { service_type }")
            return (False, ":move: failed to find ramp stop")

        # logger.debug(":move: ramp %s" % (ramp_stop))

        # find closest point on network to ramp
        rampnp = self.airport.service_roads.nearest_point_on_edge(ramp_stop)
        if rampnp[0] is None:
            logger.warning(":move: no nearest_point_on_edge for ramp_stop")
        rampnv = self.airport.service_roads.nearest_vertex(ramp_stop)
        if rampnv[0] is None:
            logger.warning(":move: no nearest_vertex for ramp_stop")

        # logger.debug(":move: ramp vertex %s" % (rampnv[0]))

        # route from start to ramp
        logger.debug(f":move: route from start {startnv[0].id} to ramp {rampnv[0].id} (vertices)")
        rt1 = Route(self.airport.service_roads, startnv[0].id, rampnv[0].id)
        # rt1.find()  # auto route
        # r1 = self.airport.service_roads.Dijkstra(startnv[0].id, rampnv[0].id)

        if rt1.found():
            for vtx in rt1.get_vertices():
                # vtx = self.airport.service_roads.get_vertex(vid)
                pos = FeatureWithProps(geometry=vtx["geometry"], properties=vtx["properties"])
                pos.setProp("_serviceroad", vtx.id)
                pos.setSpeed(speeds["normal"])
                self.moves.append(pos)
        else:
            logger.debug(f":move: no route from start {startnv[0].id} to ramp {rampnv[0].id}")

        if rampnp[0] is not None:
            rampnp[0].setSpeed(speeds["slow"])
            rampnp[0].setProp(FEATPROP.MARK.value, SERVICE_PHASE.ARRIVED.value)
            self.moves.append(rampnp[0])

        ramp_stop.setSpeed(0)
        ramp_stop.setProp(FEATPROP.MARK.value, SERVICE_PHASE.SERVICE_START.value)
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

        svc_end = ramp_stop.copy()
        svc_end.setSpeed(0)
        svc_end.setProp(FEATPROP.MARK.value, SERVICE_PHASE.SERVICE_END.value)
        self.moves.append(svc_end)

        # route ramp to end position
        if rampnp[0] is not None:
            ramp_leave = rampnp[0].copy()
            ramp_leave.setSpeed(speeds["slow"])
            ramp_leave.setProp(FEATPROP.MARK.value, SERVICE_PHASE.LEAVE.value)
            self.moves.append(ramp_leave)

        logger.debug(f":move: route from {rampnv[0].id} to {endnv[0].id}")
        r2 = Route(self.airport.service_roads, rampnv[0].id, endnv[0].id)
        if r2.found():
            for vtx in r2.get_vertices():
                pos = FeatureWithProps(geometry=vtx["geometry"], properties=vtx["properties"])
                pos.setProp("_serviceroad", vtx.id)
                pos.setSpeed(speeds["normal"])
                self.moves.append(pos)
        else:
            logger.debug(f":move: no route from ramp {rampnv[0].id} to end {endnv[0].id}")

        if endnp is not None:
            endnp[0].setSpeed(speeds["slow"])
            self.moves.append(endnp[0])

        if finalpos == startpos:
            finalpos = finalpos.copy()  # in case same as start...

        finalpos.setSpeed(0)
        finalpos.setProp(FEATPROP.MARK.value, SERVICE_PHASE.END.value)
        self.moves.append(finalpos)
        self.service.vehicle.setPosition(finalpos)

        ret = doTime(self.moves)
        if not ret[0]:
            return ret

        # printFeatures(self.moves, "route")
        printFeatures([Feature(geometry=asLineString(self.moves))], "route")

        return (False, "Service::make not implemented")


