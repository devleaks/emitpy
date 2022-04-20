"""
Build movement of a service vehicle
"""
import os
import json
import logging
from math import pi, inf
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
        return {
            "type": "service",
            "ident": self.getId(),
            "service": self.service.getInfo()
        }


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
        gseprofile = self.service.actype.gseprofile
        if gseprofile is not None:
            status = self.service.ramp.makeServicePOIs(self.service.actype)
            if not status[0]:
                logger.warning(f":move:create ramp service points failed {self.service.actype.getInfo()}")
            else:
                logger.debug(f':move:created ramp service points {list(gseprofile["services"].keys())}')

        ramp_stop = self.service.ramp.getServicePOI(service_type)
        if ramp_stop is None:
            logger.warning(f":move: failed to find ramp stop for { service_type }, using ramp center")
            ramp_stop = self.service.ramp  # use center of ramp

        if ramp_stop is None:
            logger.warning(f":move: failed to find ramp stop and/or center for { service_type }")
            return (False, ":move: failed to find ramp stop")

        # logger.debug(":move: ramp %s" % (ramp_stop))

        # find closest point on network to ramp
        ramp_npe = self.airport.service_roads.nearest_point_on_edge(ramp_stop)
        if ramp_npe[0] is None:
            logger.warning(":move: no nearest_point_on_edge for ramp_stop")
        ramp_nv = self.airport.service_roads.nearest_vertex(ramp_stop)
        if ramp_nv[0] is None:
            logger.warning(":move: no nearest_vertex for ramp_stop")

        # logger.debug(":move: ramp vertex %s" % (ramp_nv[0]))

        # route from start to ramp
        logger.debug(f":move: route from start {startnv[0].id} to ramp {ramp_nv[0].id} (vertices)")
        rt1 = Route(self.airport.service_roads, startnv[0].id, ramp_nv[0].id)
        # rt1.find()  # auto route
        # r1 = self.airport.service_roads.Dijkstra(startnv[0].id, ramp_nv[0].id)

        if rt1.found():
            for vtx in rt1.get_vertices():
                # vtx = self.airport.service_roads.get_vertex(vid)
                pos = FeatureWithProps(geometry=vtx["geometry"], properties=vtx["properties"])
                pos.setProp("_serviceroad", vtx.id)
                pos.setSpeed(speeds["normal"])
                self.moves.append(pos)
        else:
            logger.debug(f":move: no route from start {startnv[0].id} to ramp {ramp_nv[0].id}")

        if ramp_npe[0] is not None:
            ramp_npe[0].setSpeed(speeds["slow"])
            ramp_npe[0].setProp(FEATPROP.MARK.value, SERVICE_PHASE.ARRIVED.value)
            self.moves.append(ramp_npe[0])

        ramp_stop.setSpeed(0)
        ramp_stop.setProp(FEATPROP.MARK.value, SERVICE_PHASE.SERVICE_START.value)
        self.moves.append(ramp_stop)

        self.service.vehicle.setPosition(ramp_stop)

        # .. servicing ..
        # before service, may first go to ramp rest area.
        # after service, may first go to ramp rest area before leaving ramp.
        #
        # find end position if none is given

        finalpos = self.service.vehicle.next_position
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
        if ramp_npe[0] is not None:
            ramp_leave = ramp_npe[0].copy()
            ramp_leave.setSpeed(speeds["slow"])
            ramp_leave.setProp(FEATPROP.MARK.value, SERVICE_PHASE.LEAVE.value)
            self.moves.append(ramp_leave)

        logger.debug(f":move: route from {ramp_nv[0].id} to {endnv[0].id}")
        r2 = Route(self.airport.service_roads, ramp_nv[0].id, endnv[0].id)
        if r2.found():
            for vtx in r2.get_vertices():
                pos = FeatureWithProps(geometry=vtx["geometry"], properties=vtx["properties"])
                pos.setProp("_serviceroad", vtx.id)
                pos.setSpeed(speeds["normal"])
                self.moves.append(pos)
        else:
            logger.debug(f":move: no route from ramp {ramp_nv[0].id} to end {endnv[0].id}")

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
        # printFeatures([Feature(geometry=asLineString(self.moves))], "route")

        logger.debug(f":move: generated {len(self.moves)} points")
        return (True, "Service::move completed")


    def move_loop(self):
        # BEGINNING OF LOOP, go to ramp
        #
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
        gseprofile = self.service.actype.gseprofile
        if gseprofile is not None:
            status = self.service.ramp.makeServicePOIs(self.service.actype)
            if not status[0]:
                logger.warning(f":move:create ramp service points failed {gseprofile}")
            else:
                logger.debug(f':move:created ramp service points {list(gseprofile["services"].keys())}')

        ramp_stop = self.service.ramp.getServicePOI(service_type)

        if ramp_stop is None:
            logger.warning(f":move: failed to find ramp stop for { service_type }, using ramp center")
            ramp_stop = self.service.ramp  # use center of ramp

        if ramp_stop is None:
            logger.warning(f":move: failed to find ramp stop and/or center for { service_type }")
            return (False, ":move: failed to find ramp stop")

        # logger.debug(":move: ramp %s" % (ramp_stop))

        # find closest point on network to ramp
        ramp_npe = self.airport.service_roads.nearest_point_on_edge(ramp_stop)
        if ramp_npe[0] is None:
            logger.warning(":move: no nearest_point_on_edge for ramp_stop")
        ramp_nv = self.airport.service_roads.nearest_vertex(ramp_stop)
        if ramp_nv[0] is None:
            logger.warning(":move: no nearest_vertex for ramp_stop")

        # logger.debug(":move: ramp vertex %s" % (ramp_nv[0]))

        # route from start to ramp
        logger.debug(f":move: route from start {startnv[0].id} to ramp {ramp_nv[0].id} (vertices)")
        rt1 = Route(self.airport.service_roads, startnv[0].id, ramp_nv[0].id)
        # rt1.find()  # auto route
        # r1 = self.airport.service_roads.Dijkstra(startnv[0].id, ramp_nv[0].id)

        if rt1.found():
            for vtx in rt1.get_vertices():
                # vtx = self.airport.service_roads.get_vertex(vid)
                pos = FeatureWithProps(geometry=vtx["geometry"], properties=vtx["properties"])
                pos.setProp("_serviceroad", vtx.id)
                pos.setSpeed(speeds["normal"])
                self.moves.append(pos)
        else:
            logger.debug(f":move: no route from start {startnv[0].id} to ramp {ramp_nv[0].id}")

        if ramp_npe[0] is not None:
            ramp_npe[0].setSpeed(speeds["slow"])
            ramp_npe[0].setProp(FEATPROP.MARK.value, SERVICE_PHASE.ARRIVED.value)
            self.moves.append(ramp_npe[0])

        ramp_stop.setSpeed(0)
        ramp_stop.setProp(FEATPROP.MARK.value, SERVICE_PHASE.SERVICE_START.value)
        self.moves.append(ramp_stop)

        self.service.vehicle.setPosition(ramp_stop)

        # .. servicing ..
        # before service, may first go to ramp rest area.
        # after service, may first go to ramp rest area before leaving ramp.
        #
        # LOOP, go to next position
        looping = True
        if looping:
            # Prepare nearest depot
            nearest_depot = self.airport.getNearestServiceDepot(service_type, ramp_stop)
            nd_npe = self.airport.service_roads.nearest_point_on_edge(nearest_depot)
            if nd_npe[0] is None:
                    logger.warning(":move: no nearest_point_on_edge for nearest_depot")
            nd_nv = self.airport.service_roads.nearest_vertex(nearest_depot)
            if nd_nv[0] is None:
                logger.warning(":move: no nearest_vertex for nearest_depot")
            # route ramp -> nearest depot
            logger.debug(f":move: route from ramp {ramp_nv[0].id} to nearest depot {nd_nv[0].id} (vertices)")
            go_unload = Route(self.airport.service_roads, ramp_nv[0].id, nd_nv[0].id)
            if not go_unload.found():
                logger.warning(":move: no route from ramp to nearest depot")
            go_load = Route(self.airport.service_roads, nd_nv[0].id, ramp_nv[0].id)
            if not go_load.found():
                logger.warning(":move: no route from nearest depot to ramp")
            logger.debug(":move: ready to loop")
            vehicle = self.service.vehicle
            service = self.service
            logger.debug(f":move: vehicle capacity {vehicle.max_capacity}, current load {vehicle.current_load}")
            vehicle_capacity = vehicle.max_capacity - vehicle.current_load  # may not be empty when it arrives
            while self.service.quantity > 0:
                #
                # Fill vehicle, decrease service quantity
                if vehicle.max_capacity == inf:  # infinite capacity; served in one trip
                    vehicle.current_load = service.quantity
                    svc_duration = vehicle.service_duration(service.quantity)
                    service.quantity = 0
                elif service.quantity < vehicle_capacity:  # one last trip
                    vehicle.current_load = vehicle.current_load + service.quantity
                    svc_duration = vehicle.service_duration(service.quantity)
                    logger.debug(f":move: loaded {service.quantity}, 0 remaining")
                    service.quantity = 0
                else:
                    logger.debug(f":move: loaded {vehicle_capacity}, {service.quantity - vehicle_capacity} remaining")
                    vehicle.current_load = vehicle.max_capacity
                    svc_duration = vehicle.service_duration(vehicle.max_capacity)
                    service.quantity = service.quantity - vehicle_capacity

                logger.debug(f":move: loaded {vehicle_capacity}, {service.quantity - vehicle_capacity} remaining, load duration={svc_duration}")
                ramp_stop.pause(svc_duration)

                # go to nearest depot
                # ramp->network edge
                pos = FeatureWithProps(geometry=ramp_npe[0]["geometry"], properties=ramp_npe[0]["properties"])
                pos.setSpeed(speeds["slow"])
                self.moves.append(pos)
                # network edge->network vertex
                pos = FeatureWithProps(geometry=nd_nv[0]["geometry"], properties=nd_nv[0]["properties"])
                pos.setProp("_serviceroad", nd_nv[0].id)
                pos.setSpeed(speeds["slow"])
                self.moves.append(pos)
                # network vertex->network vertex
                if go_unload.found():
                    for vtx in go_unload.get_vertices():
                        # vtx = self.airport.service_roads.get_vertex(vid)
                        pos = FeatureWithProps(geometry=vtx["geometry"], properties=vtx["properties"])
                        pos.setProp("_serviceroad", vtx.id)
                        pos.setSpeed(speeds["normal"])
                        self.moves.append(pos)
                else:
                    logger.debug(f":move: no route from ramp {ramp_nv[0].id} to nearest depot {nd_nv[0].id}")
                # network vertex->network edge (close to depot)
                pos = FeatureWithProps(geometry=nd_npe[0]["geometry"], properties=nd_npe[0]["properties"])
                pos.setSpeed(speeds["slow"])
                self.moves.append(pos)
                # network edge-> depot
                pos = FeatureWithProps(geometry=nearest_depot["geometry"], properties=nearest_depot["properties"])
                pos.setSpeed(speeds["slow"])
                self.moves.append(pos)

                #
                # Empty vehicle
                vehicle.setPosition(pos)
                svc_duration = vehicle.service_duration(vehicle.current_load)
                logger.debug(f":move: unloaded {vehicle.current_load}, {service.quantity} remaining, unload duration={svc_duration}")
                pos.pause(svc_duration)

                vehicle.current_load = 0
                vehicle_capacity = vehicle.max_capacity

                # go back to ramp
                # depot ->network edge (close to depot)
                pos = FeatureWithProps(geometry=nd_npe[0]["geometry"], properties=nd_npe[0]["properties"])
                pos.setSpeed(speeds["slow"])
                self.moves.append(pos)
                # network edge->network vertex (close to depot)
                pos = FeatureWithProps(geometry=nd_nv[0]["geometry"], properties=nd_nv[0]["properties"])
                pos.setSpeed(speeds["slow"])
                self.moves.append(pos)
                # network vertex->network vertex
                if go_load.found():
                    for vtx in go_load.get_vertices():
                        # vtx = self.airport.service_roads.get_vertex(vid)
                        pos = FeatureWithProps(geometry=vtx["geometry"], properties=vtx["properties"])
                        pos.setProp("_serviceroad", vtx.id)
                        pos.setSpeed(speeds["normal"])
                        self.moves.append(pos)
                else:
                    logger.debug(f":move: no route from nearest depot {nd_nv[0].id} to ramp {ramp_nv[0].id}")
                # ramp->network edge
                pos = FeatureWithProps(geometry=ramp_npe[0]["geometry"], properties=ramp_npe[0]["properties"])
                pos.setSpeed(speeds["slow"])
                self.moves.append(pos)
                # network edge->ramp
                pos = FeatureWithProps(geometry=ramp_stop["geometry"], properties=ramp_stop["properties"])
                pos.setSpeed(speeds["slow"])
                self.moves.append(pos)


        # END OF LOOP, go to next position
        #
        # find end position if none is given
        finalpos = self.service.vehicle.next_position
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
        if ramp_npe[0] is not None:
            ramp_leave = ramp_npe[0].copy()
            ramp_leave.setSpeed(speeds["slow"])
            ramp_leave.setProp(FEATPROP.MARK.value, SERVICE_PHASE.LEAVE.value)
            self.moves.append(ramp_leave)

        logger.debug(f":move: route from {ramp_nv[0].id} to {endnv[0].id}")
        r2 = Route(self.airport.service_roads, ramp_nv[0].id, endnv[0].id)
        if r2.found():
            for vtx in r2.get_vertices():
                pos = FeatureWithProps(geometry=vtx["geometry"], properties=vtx["properties"])
                pos.setProp("_serviceroad", vtx.id)
                pos.setSpeed(speeds["normal"])
                self.moves.append(pos)
        else:
            logger.debug(f":move: no route from ramp {ramp_nv[0].id} to end {endnv[0].id}")

        if endnp is not None:
            endnp[0].setSpeed(speeds["slow"])
            self.moves.append(endnp[0])

        if finalpos == startpos:
            finalpos = finalpos.copy()  # in case same as start...

        finalpos.setSpeed(0)
        finalpos.setProp(FEATPROP.MARK.value, SERVICE_PHASE.END.value)
        self.moves.append(finalpos)
        self.service.vehicle.setPosition(finalpos)

        # No interpolation necessary:
        # Each point should have speed set, altitude and vspeed irrelevant.
        ret = doTime(self.moves)
        if not ret[0]:
            return ret

        # printFeatures(self.moves, "route")
        printFeatures([Feature(geometry=asLineString(self.moves))], "route")

        logger.debug(f":move: generated {len(self.moves)} points")
        return (False, "Service::make not implemented")

