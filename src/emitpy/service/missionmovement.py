"""
Build movement of a equipment
"""

import logging

from emitpy.airport import ManagedAirportBase
from emitpy.geo import MovePoint, Movement
from emitpy.service import Mission
from emitpy.graph import Route
from emitpy.utils import compute_time as doTime
from emitpy.constants import FEATPROP, MISSION_PHASE, MISSION_COLOR, MOVE_TYPE
from emitpy.message import MissionMessage
from .ground_support_movement import GroundSupportMovement

logger = logging.getLogger("ServiceMovement")


class MissionMove(GroundSupportMovement):
    """
    Movement build the detailed path of the aircraft, both on the ground (taxi) and in the air,
    from takeoff to landing and roll out.
    """

    def __init__(self, mission: Mission, airport: ManagedAirportBase):
        GroundSupportMovement.__init__(self, airport=airport, reason=mission)
        self.mission = mission

    def getId(self):
        return self.mission.getId()

    def getInfo(self):
        return {
            "type": MOVE_TYPE.MISSION.value,
            "ident": self.getId(),
            "mission": self.mission.getInfo(),
            "icao24": self.mission.getInfo()["icao24"],
        }

    def getSource(self):
        return self.mission

    def drive(self):
        move_points = self.getMovePoints()
        last_vtx = None
        speeds = self.mission.vehicle.speed

        start_pos = self.mission.vehicle.getPosition()
        pos = MovePoint.new(start_pos)

        pos.setSpeed(0)  # starts at rest
        pos.setMark(MISSION_PHASE.START.value)
        pos.setColor(MISSION_COLOR.START.value)
        move_points.append(pos)
        logger.debug(f"start added")

        self.addMessage(
            MissionMessage(
                subject=f"{self.mission.vehicle.icao24} {MISSION_PHASE.START.value}",
                mission=self,
                sync=MISSION_PHASE.START.value,
                info=self.getInfo(),
            )
        )

        self.addMessage(
            MissionMessage(
                subject=f"Mission {self.getId()} has started",
                mission=self,
                sync=MISSION_PHASE.START.value,
                info=self.getInfo(),
                service=MISSION_PHASE.START.value,
            )
        )

        # starting position to network
        start_npe = self.airport.service_roads.nearest_point_on_edge(start_pos)
        if start_npe[0] is None:
            logger.warning("no nearest_point_on_edge for start_pos")
        else:
            pos = start_npe[0]
            pos.setSpeed(speeds["slow"])  # starts moving
            pos.setMark(MISSION_PHASE.EN_ROUTE.value)
            pos.setColor(MISSION_COLOR.EN_ROUTE.value)
            move_points.append(pos)

        # logger.debug("start vertex %s" % (start_npe[0]))
        # Find first vertex
        start_nv = self.airport.service_roads.nearest_vertex(start_pos)
        if start_nv[0] is None:
            logger.warning("no nearest_vertex for start_pos")
        # will move to it as first point of rt Route()

        ## Mission loop:
        prev_cp = start_nv
        prev_vtx = start_nv[0]
        chkpt_cnt = 0
        for cp_id in self.mission.checkpoints:
            # We enter at the last service_road network vertex.
            cp = self.airport.getControlPoint(
                cp_id
            )  # list of checkpoints extended to all POI and stops.
            if cp is None:
                logger.warning(f"cannot find checkpoint {cp_id}")
                continue
            logger.warning(f"going to checkpoint {cp_id}")

            # find closest vertex of next control point
            cp_nv = self.airport.service_roads.nearest_vertex(cp)
            if cp_nv[0] is None:
                logger.warning(
                    f"no nearest_vertex for checkpoint {cp.getPprop('name')}"
                )
            # logger.debug("cp vertex %s" % (cp_nv[0]))

            # route from previous vtx to this one
            logger.debug(f"route from {prev_vtx.id} to {cp_nv[0].id}")
            rt = Route(self.airport.service_roads, prev_vtx.id, cp_nv[0].id)
            # rt1.find()  # auto route
            # r1 = self.airport.service_roads.Dijkstra(start_nv[0].id, cp_nv[0].id)

            last_vtx = None
            if rt.found():
                for vtx in rt.get_vertices():
                    # vtx = self.airport.service_roads.get_vertex(vid)
                    pos = MovePoint.new(vtx)
                    pos.setProp("_serviceroad", vtx.id)
                    pos.setSpeed(speeds["normal"])
                    pos.setMark(MISSION_PHASE.EN_ROUTE.value)
                    pos.setColor(MISSION_COLOR.EN_ROUTE.value)
                    move_points.append(pos)
                    last_vtx = vtx
            else:
                logger.debug(f"no route from {prev_vtx.id} to {cp_nv[0].id}")

            # find closest point on network to checkpoint
            # logger.debug(f"route to checkpoint {cp}")
            cp_npe = self.airport.service_roads.nearest_point_on_edge(cp)
            if cp_npe[0] is None:
                logger.warning(
                    f"no nearest_point_on_edge for checkpoint {cp.getPprop('name')}"
                )
            else:  # move to it
                pos = MovePoint.new(cp_npe[0])
                pos.setSpeed(speeds["slow"])  # starts moving
                pos.setMark(MISSION_PHASE.EN_ROUTE.value)
                pos.setColor(MISSION_COLOR.EN_ROUTE.value)
                move_points.append(pos)

            # finally reaches checkpoint
            pos = MovePoint.new(cp)
            pos.setSpeed(0)  # starts moving
            pos.setMark(MISSION_PHASE.CHECKPOINT.value)
            pos.setProp(FEATPROP.MARK_SEQUENCE, chkpt_cnt)
            pos.setColor(MISSION_COLOR.CHECKPOINT.value)
            pos.setPause(self.mission.duration(cp))
            move_points.append(pos)
            logger.debug(f"checkpoint added")

            self.addMessage(
                MissionMessage(
                    subject=f"Mission {self.getId()} reached control point {cp_id}",
                    mission=self,
                    sync=MISSION_PHASE.CHECKPOINT.value,
                    info=self.getInfo(),
                    service=MISSION_PHASE.CHECKPOINT.value,
                )
            )

            # goes back on service road network (edge)
            if cp_npe[0] is None:
                logger.warning(
                    f"no nearest_point_on_edge for checkpoint {cp.getPprop('name')}"
                )
            else:  # move to it
                pos = MovePoint.new(cp_npe[0])
                pos.setSpeed(speeds["slow"])  # starts moving
                pos.setMark(MISSION_PHASE.EN_ROUTE.value)
                pos.setColor(MISSION_COLOR.EN_ROUTE.value)
                move_points.append(pos)

            # goes back on service road network at closest vertex
            if last_vtx is not None:  # back on service road
                move_points.append(pos)
                prev_vtx = last_vtx

            prev_cp = cp
            chkpt_cnt = chkpt_cnt + 1

        # Goes to next position, or back to start position if no next position.
        final_pos = self.mission.vehicle.next_position
        if final_pos is not None:
            # end position to network
            final_npe = self.airport.service_roads.nearest_point_on_edge(final_pos)
            if final_npe[0] is None:
                logger.warning("no nearest_point_on_edge for finalpos")
            # logger.debug("start vertex %s" % (start_npe[0]))
            final_nv = self.airport.service_roads.nearest_vertex(final_pos)
            if final_nv[0] is None:
                logger.warning("no nearest_vertex for finalpos")
        else:
            final_pos = start_pos
            final_npe = start_npe
            final_nv = start_nv

        if last_vtx is None:
            # Issue here: Why is last_vtx sometimes null?
            logger.warning(
                "no last vertex because no route to last checkpoint, using previous point"
            )
            last_vtx = prev_vtx  # ?

        # Route from last checkpoint to closest vertex to final_pos
        rt = Route(self.airport.service_roads, last_vtx.id, final_nv[0].id)
        if rt.found():
            for vtx in rt.get_vertices():
                # vtx = self.airport.service_roads.get_vertex(vid)
                pos = MovePoint.new(vtx)
                pos.setProp("_serviceroad", vtx.id)
                pos.setMark(MISSION_PHASE.EN_ROUTE.value)
                pos.setColor(MISSION_COLOR.EN_ROUTE.value)
                pos.setSpeed(speeds["normal"])
                move_points.append(pos)
        else:
            logger.debug(
                f"no route from last checkpoint vtx {prev_vtx.id} to final destination vtx {cp_nv[0].id}"
            )

        # from vertex to closest point on service road network to final_pos
        pos = final_npe[0]
        pos.setSpeed(speeds["slow"])
        pos.setMark(MISSION_PHASE.EN_ROUTE.value)
        pos.setColor(MISSION_COLOR.EN_ROUTE.value)
        move_points.append(pos)

        # from closest point on service road network to final_pos, stops there
        pos = MovePoint.new(final_pos)
        pos.setSpeed(0)  # ends at rest
        pos.setMark(MISSION_PHASE.END.value)
        pos.setColor(MISSION_COLOR.END.value)
        move_points.append(pos)

        self.addMessage(
            MissionMessage(
                subject=f"Mission {self.getId()} has ended",
                mission=self,
                sync=MISSION_PHASE.END.value,
                info=self.getInfo(),
                service=MISSION_PHASE.END.value,
            )
        )

        self.addMessage(
            MissionMessage(
                subject=f"{self.mission.vehicle.icao24} {MISSION_PHASE.END.value}",
                mission=self,
                sync=MISSION_PHASE.END.value,
                info=self.getInfo(),
            )
        )

        logger.debug(f"end added")

        # No interpolation necessary:
        # Each point should have speed set, altitude and vspeed irrelevant.
        ret = doTime(self.getMovePoints())
        if not ret[0]:
            return ret

        # Sets unique index on mission movement features
        idx = 0
        for f in self.getMovePoints():
            f.setProp(FEATPROP.MOVE_INDEX, idx)
            idx = idx + 1

        return (True, "Mission::drive completed")
