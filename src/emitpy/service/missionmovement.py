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
from ..geo import MovePoint, Movement, FeatureWithProps
from ..service import Mission, ServiceVehicle
from ..graph import Route
from ..utils import compute_time as doTime
from ..constants import FEATPROP, MISSION_PHASE, MISSION_COLOR

logger = logging.getLogger("ServiceMove")


class MissionMove(Movement):
    """
    Movement build the detailed path of the aircraft, both on the ground (taxi) and in the air,
    from takeoff to landing and roll out.
    """
    def __init__(self, mission: Mission, airport: AirportBase):
        Movement.__init__(self, airport=airport)
        self.mission = mission


    def getId(self):
        return self.mission.getId()


    def getInfo(self):
        return self.mission.getInfo()


    def move(self):
        speeds = self.mission.vehicle.speed

        start_pos = self.mission.vehicle.getPosition()
        # logger.debug(":move: start position %s" % (start_pos))

        start_pos.setSpeed(0)  # starts at rest
        start_pos.setProp(FEATPROP.MARK.value, MISSION_PHASE.START.value)
        start_pos.setColor(MISSION_COLOR.START.value)
        self.moves.append(start_pos)

        # starting position to network
        start_npe = self.airport.service_roads.nearest_point_on_edge(start_pos)
        if start_npe[0] is None:
            logger.warning(":move: no nearest_point_on_edge for start_pos")
        else:
            pos = start_npe[0]
            pos.setSpeed(speeds["slow"])  # starts moving
            pos.setProp(FEATPROP.MARK.value, MISSION_PHASE.EN_ROUTE.value)
            pos.setColor(MISSION_COLOR.EN_ROUTE.value)
            self.moves.append(pos)


        # logger.debug(":move: start vertex %s" % (start_npe[0]))
        # Find first vertex
        start_nv = self.airport.service_roads.nearest_vertex(start_pos)
        if start_nv[0] is None:
            logger.warning(":move: no nearest_vertex for start_pos")
        # will move to it as first point of rt Route()

        ## Mission loop:
        prev_cp = start_nv
        prev_vtx = start_nv[0]
        for cp_id in self.mission.checkpoints:
            # We enter at the last service_road network vertex.
            cp = self.airport.getControlPoint(cp_id)  # list of checkpoints extended to all POI and stops.
            if cp is None:
                logger.warning(f":move: cannot find checkpoint {cp_id}")
                continue

            # find closest vertex of next control point
            cp_nv = self.airport.service_roads.nearest_vertex(cp)
            if cp_nv[0] is None:
                logger.warning(f":move: no nearest_vertex for checkpoint {cp.getPprop('name')}")
            # logger.debug(":move: cp vertex %s" % (cp_nv[0]))

            # route from previous vtx to this one
            logger.debug(f":move: route from {prev_vtx.id} to {cp_nv[0].id}")
            rt = Route(self.airport.service_roads, prev_vtx.id, cp_nv[0].id)
            # rt1.find()  # auto route
            # r1 = self.airport.service_roads.Dijkstra(start_nv[0].id, cp_nv[0].id)

            last_vtx = None
            if rt.found():
                for vtx in rt.get_vertices():
                    # vtx = self.airport.service_roads.get_vertex(vid)
                    pos = FeatureWithProps(geometry=vtx["geometry"], properties=vtx["properties"])
                    pos.setProp("_serviceroad", vtx.id)
                    pos.setSpeed(speeds["normal"])
                    pos.setProp(FEATPROP.MARK.value, MISSION_PHASE.EN_ROUTE.value)
                    pos.setColor(MISSION_COLOR.EN_ROUTE.value)
                    self.moves.append(pos)
                    last_vtx = vtx
            else:
                logger.debug(f":move: no route from {prev_vtx.id} to {cp_nv[0].id}")

            # find closest point on network to checkpoint
            # logger.debug(f":move: route to checkpoint {cp}")
            cp_npe = self.airport.service_roads.nearest_point_on_edge(cp)
            if cp_npe[0] is None:
                logger.warning(f":move: no nearest_point_on_edge for checkpoint {cp.getPprop('name')}")
            else:  # move to it
                pos = cp_npe[0]
                pos.setSpeed(speeds["slow"])  # starts moving
                pos.setProp(FEATPROP.MARK.value, MISSION_PHASE.EN_ROUTE.value)
                pos.setColor(MISSION_COLOR.EN_ROUTE.value)
                self.moves.append(pos)

            # finally reaches checkpoint
            pos = FeatureWithProps(geometry=cp["geometry"], properties=cp["properties"])
            pos.setSpeed(0)  # starts moving
            pos.setProp(FEATPROP.MARK.value, MISSION_PHASE.CHECKPOINT.value)
            pos.setColor(MISSION_COLOR.CHECKPOINT.value)
            pos.pause(self.mission.missionDuration(cp))
            self.moves.append(pos)

            # goes back on service road network (edge)
            if cp_npe[0] is None:
                logger.warning(f":move: no nearest_point_on_edge for checkpoint {cp.getPprop('name')}")
            else:  # move to it
                pos = cp_npe[0]
                pos.setSpeed(speeds["slow"])  # starts moving
                pos.setProp(FEATPROP.MARK.value, MISSION_PHASE.EN_ROUTE.value)
                pos.setColor(MISSION_COLOR.EN_ROUTE.value)
                self.moves.append(pos)

            # goes back on service road network at closest vertex
            if last_vtx is not None:  # back on service road
                self.moves.append(pos)
                prev_vtx = last_vtx

            prev_cp = cp

        # Goes to next position, or back to start position if no next position.
        final_pos = self.mission.vehicle.next_position
        if final_pos is not None:
            # end position to network
            final_npe = self.airport.service_roads.nearest_point_on_edge(final_pos)
            if final_npe[0] is None:
                logger.warning(":move: no nearest_point_on_edge for finalpos")
            # logger.debug(":move: start vertex %s" % (start_npe[0]))
            final_nv = self.airport.service_roads.nearest_vertex(final_pos)
            if final_nv[0] is None:
                logger.warning(":move: no nearest_vertex for finalpos")
        else:
            final_pos = start_pos
            final_npe = start_npe
            final_nv = start_nv

        # Route from last checkpoint to closest vertex to final_pos
        rt = Route(self.airport.service_roads, last_vtx.id, final_nv[0].id)
        if rt.found():
            for vtx in rt.get_vertices():
                # vtx = self.airport.service_roads.get_vertex(vid)
                pos = FeatureWithProps(geometry=vtx["geometry"], properties=vtx["properties"])
                pos.setProp("_serviceroad", vtx.id)
                pos.setProp(FEATPROP.MARK.value, MISSION_PHASE.EN_ROUTE.value)
                pos.setColor(MISSION_COLOR.EN_ROUTE.value)
                pos.setSpeed(speeds["normal"])
                self.moves.append(pos)
        else:
            logger.debug(f":move: no route from last checkpoint vtx {prev_vtx.id} to final destination vtx {cp_nv[0].id}")

        # from vertex to closest point on service road network to final_pos
        pos = final_npe[0]
        pos.setSpeed(speeds["slow"])
        pos.setProp(FEATPROP.MARK.value, MISSION_PHASE.EN_ROUTE.value)
        pos.setColor(MISSION_COLOR.EN_ROUTE.value)
        self.moves.append(pos)

        # from closest point on service road network to final_pos, stops there
        final_pos.setSpeed(0)  # ends at rest
        final_pos.setProp(FEATPROP.MARK.value, MISSION_PHASE.END.value)
        pos.setColor(MISSION_COLOR.END.value)
        self.moves.append(final_pos)

        return (True, "Mission::move completed")

