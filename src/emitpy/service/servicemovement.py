"""
Build movement of a equipment
"""
import logging
from math import inf


from geojson import Feature

from emitpy.airport import ManagedAirportBase
from emitpy.geo import MovePoint, Movement, printFeatures, asLineString
from emitpy.service import Service
from emitpy.graph import Route
from emitpy.utils import compute_time as doTime
from emitpy.constants import FEATPROP, SERVICE_PHASE, MOVE_TYPE
from emitpy.message import ServiceMessage

logger = logging.getLogger("ServiceMove")

MOVE_LOOP = ["BaggageService"]  # , "cargo"


class ServiceMove(Movement):
    """
    Movement build the detailed path of the aircraft, both on the ground (taxi) and in the air,
    from takeoff to landing and roll out.
    """
    def __init__(self, service: Service, airport: ManagedAirportBase):
        Movement.__init__(self, airport=airport)
        self.service = service


    def getId(self):
        return self.service.getId()


    def getInfo(self):
        return {
            "type": MOVE_TYPE.SERVICE.value,
            "ident": self.getId(),
            "service": self.service.getInfo(),
            "icao24": self.service.getInfo()["icao24"]
        }


    def getSource(self):
        # Abstract class
        return self.service


    def no_move(self):
        """
        No movement associated with this service, just emit ServiceMessage at event time.
        Since there is no movement associated, there is no sync label to be used.
        So the relative time will be relative to the supplied scheduled time, which normally is ONBLOCK/OFFBLOCK time.
        """
        if self.service.pts_duration == 0:
            self.addMessage(ServiceMessage(subject=f"«{self.service.label}» occured",
                                           service=self,
                                           sync=SERVICE_PHASE.START.value,
                                           info=self.getInfo()))
            logger.debug(f"{self.service.name} added 1 messages")
        else:
            self.addMessage(ServiceMessage(subject=f"«{self.service.label}» {SERVICE_PHASE.START.value}",
                                           service=self,
                                           sync=SERVICE_PHASE.START.value,
                                           info=self.getInfo()))
            # End time is start time + duration, we add duration as a delay relative to the start time
            self.addMessage(ServiceMessage(subject=f"«{self.service.label}» {SERVICE_PHASE.END.value}",
                                           service=self,
                                           sync=SERVICE_PHASE.END.value,
                                           info=self.getInfo(),
                                           relative_time=(self.service.pts_duration * 60)))  # minutes
            logger.debug(f"{self.service.name} added 2 messages")


    def move(self):
        # Special case 1: Service "event reporting only", no move
        if self.service.vehicle is None:  # Service with no vehicle movement
            logger.debug(f"service {type(self.service).__name__} «{self.service.label}» has no vehicle, assuming event report only")
            self.no_move()
            logger.debug(f"generated {len(self.moves)} points")
            return (True, "ServiceMove::move: no moves, assuming event report only")

        # Special case 2: Service vehicle going back and forth between ramp and depot
        if type(self.service).__name__ in MOVE_LOOP:
            logger.debug(f"moving loop for {type(self.service).__name__}..")
            ret = self.move_loop()
            if ret[0]:
                logger.debug(f"..moved")
                return (True, "ServiceMove::move completed")  # return ret?
            logger.warning(ret[1])
            logger.debug(f"..loop did not complete successfully, using normal move..")

        # Normal case:
        speeds = self.service.vehicle.speed

        startpos = self.service.vehicle.getPosition()
        if startpos is None:
            logger.warning(f"no start position for {self.service.vehicle.getId()}")
        service_type = type(self.service).__name__.replace("Service", "").lower()

        startpos.setSpeed(0)  # starts at rest
        startpos.setProp(FEATPROP.MARK.value, SERVICE_PHASE.START.value)
        self.moves.append(startpos)

        self.addMessage(ServiceMessage(subject=f"{self.service.vehicle.icao24} {SERVICE_PHASE.START.value}",
                                       service=self,
                                       sync=SERVICE_PHASE.START.value,
                                       info=self.getInfo()))

        # starting position to network
        startnp = self.airport.service_roads.nearest_point_on_edge(startpos)
        if startnp[0] is None:
            logger.warning("no nearest_point_on_edge for startpos")
        else:
            startnp[0].setSpeed(speeds["slow"])  # starts moving
            self.moves.append(startnp[0])

        # logger.debug("start vertex %s" % (startnp[0]))

        startnv = self.airport.service_roads.nearest_vertex(startpos)
        if startnv[0] is None:
            logger.warning("no nearest_vertex for startpos")

        # find ramp position, use ramp center if none is given
        gseprofile = self.service.actype.getGSEProfile()
        if gseprofile is not None:
            status = self.service.ramp.makeServicePOIs(self.service.actype)
            if not status[0]:
                logger.warning(f"create ramp service points failed {self.service.actype.getInfo()}")
            # else:
            #     logger.debug(f'created ramp service points {list(gseprofile["services"].keys())}')

        ramp_stop = self.service.ramp.getServicePOI(service_type, self.service.actype)
        wer = service_type
        if ramp_stop is None:
            logger.warning(f"failed to find ramp stop for { self.service.actype.typeId }, { service_type }, using ramp center")
            ramp_stop = self.service.ramp  # use center of ramp
            wer = "center"

        if ramp_stop is None:
            logger.warning(f"failed to find ramp stop and/or center for { service_type }")
            return (False, ":move: failed to find ramp stop")

        # logger.debug("ramp %s" % (ramp_stop))

        # find closest point on network to ramp
        ramp_npe = self.airport.service_roads.nearest_point_on_edge(ramp_stop)
        if ramp_npe[0] is None:
            logger.warning(f"no nearest_point_on_edge for ramp_stop ({wer})")
        ramp_nv = self.airport.service_roads.nearest_vertex(ramp_stop)
        if ramp_nv[0] is None:
            logger.warning(f"no nearest_vertex for ramp_stop ({wer})")

        # logger.debug("ramp vertex %s" % (ramp_nv[0]))

        # route from start to ramp
        logger.debug(f"route from start {startnv[0].id} to ramp/{wer} {ramp_nv[0].id} (vertices)")
        rt1 = Route(self.airport.service_roads, startnv[0].id, ramp_nv[0].id)
        # rt1.find()  # auto route
        # r1 = self.airport.service_roads.Dijkstra(startnv[0].id, ramp_nv[0].id)

        if rt1.found():
            for vtx in rt1.get_vertices():
                # vtx = self.airport.service_roads.get_vertex(vid)
                pos = MovePoint.new(vtx)
                pos.setProp("_serviceroad", vtx.id)
                pos.setSpeed(speeds["normal"])
                self.moves.append(pos)
        else:
            logger.debug(f"no route from start {startnv[0].id} to ramp {ramp_nv[0].id}")

        if ramp_npe[0] is not None:
            ramp_npe[0].setSpeed(speeds["slow"])
            ramp_npe[0].setProp(FEATPROP.MARK.value, SERVICE_PHASE.ARRIVED.value)
            self.moves.append(ramp_npe[0])

        self.addMessage(ServiceMessage(subject=f"{self.service.vehicle.icao24} {SERVICE_PHASE.ARRIVED.value}",
                                       service=self,
                                       sync=SERVICE_PHASE.ARRIVED.value,
                                       info=self.getInfo()))
        # ###
        # If there is a stop poi named "STANDBY" and if the service has pause_before > 0
        # we first go to the standby position and wait pause_before minutes.
        #
        ramp_standby = self.service.ramp.getServicePOI("standby", self.service.actype)
        if ramp_standby is not None and self.service.pause_before > 0:
            ramp_standby_pos = MovePoint.new(ramp_standby)
            ramp_standby_pos.setSpeed(0)


            ramp_standby_pos.setProp(FEATPROP.MARK.value, "standby-before-service")
            ramp_standby_pos.setPause(self.service.pause_before)
            self.moves.append(ramp_standby_pos)
            logger.debug(f"added pause {self.service.pause_before}m before service")

        ramp_stop.setSpeed(0)
        ramp_stop.setProp(FEATPROP.MARK.value, SERVICE_PHASE.SERVICE_START.value)

        # Adding service time
        service_duration = self.service.duration()
        ramp_stop.setPause(service_duration)
        logger.debug(f"service duration {service_duration}")
        self.moves.append(ramp_stop)

        self.service.vehicle.setPosition(ramp_stop)

        self.addMessage(ServiceMessage(subject=f"Service {self.getId()} has started",
                                       service=self,
                                       sync=SERVICE_PHASE.SERVICE_START.value,
                                       info=self.getInfo()))

        # .. servicing ..
        # before service, may first go to ramp rest area.
        # after service, may first go to ramp rest area before leaving ramp.
        #
        # find end position if none is given
        finalpos = self.service.vehicle.next_position
        if finalpos is None:
            finalpos = self.airport.selectRandomServiceRestArea(service_type)
            # logger.debug(f"end position { finalpos }")

            if finalpos is None:
                logger.warning(f"no end rest area for { service_type }, using start position")
                finalpos = startpos

        # find end position on network
        endnp = self.airport.service_roads.nearest_point_on_edge(finalpos)
        if endnp[0] is None:
            logger.warning("no nearest_point_on_edge for end")

        endnv = self.airport.service_roads.nearest_vertex(finalpos)
        if endnv[0] is None:
            logger.warning("no nearest_vertex for end")

        svc_end = ramp_stop.copy()
        svc_end.setSpeed(0)
        svc_end.setProp(FEATPROP.MARK.value, SERVICE_PHASE.SERVICE_END.value)
        self.moves.append(svc_end)

        self.addMessage(ServiceMessage(subject=f"Service {self.getId()} has ended",
                                       service=self,
                                       sync=SERVICE_PHASE.SERVICE_END.value,
                                       info=self.getInfo()))
        # ###
        # If there is a stop poi named "REST" and if the service has pause_after > 0
        # we first go to the rest position and wait pause_after minutes.
        #
        ramp_rest = self.service.ramp.getServicePOI("standby", self.service.actype)
        if ramp_rest is not None and self.service.pause_after > 0:
            ramp_rest_pos = MovePoint.new(ramp_rest)
            ramp_rest_pos.setSpeed(0)
            ramp_rest_pos.setProp(FEATPROP.MARK.value, "rest-after-service")
            ramp_rest_pos.setPause(self.service.pause_after)
            self.moves.append(ramp_standby_pos)
            logger.debug(f"added pause {self.service.pause_after}m after service")

        # route ramp to end position
        if ramp_npe[0] is not None:
            ramp_leave = ramp_npe[0].copy()
            ramp_leave.setSpeed(speeds["slow"])
            ramp_leave.setProp(FEATPROP.MARK.value, SERVICE_PHASE.LEAVE.value)
            self.moves.append(ramp_leave)

        self.addMessage(ServiceMessage(subject=f"{self.service.vehicle.icao24} {SERVICE_PHASE.LEAVE.value}",
                                       service=self,
                                       sync=SERVICE_PHASE.LEAVE.value,
                                       info=self.getInfo()))

        logger.debug(f"route from {ramp_nv[0].id} to {endnv[0].id}")
        r2 = Route(self.airport.service_roads, ramp_nv[0].id, endnv[0].id)
        if r2.found():
            for vtx in r2.get_vertices():
                pos = MovePoint.new(vtx)
                pos.setProp("_serviceroad", vtx.id)
                pos.setSpeed(speeds["normal"])
                self.moves.append(pos)
        else:
            logger.debug(f"no route from ramp {ramp_nv[0].id} to end {endnv[0].id}")

        if endnp is not None:
            endnp[0].setSpeed(speeds["slow"])
            self.moves.append(endnp[0])

        if finalpos == startpos:
            finalpos = finalpos.copy()  # in case same as start...

        finalpos.setSpeed(0)
        finalpos.setProp(FEATPROP.MARK.value, SERVICE_PHASE.END.value)
        self.moves.append(finalpos)
        self.service.vehicle.setPosition(finalpos)

        self.addMessage(ServiceMessage(subject=f"{self.service.vehicle.icao24} {SERVICE_PHASE.END.value}",
                                       service=self,
                                       sync=SERVICE_PHASE.END.value,
                                       info=self.getInfo()))

        ret = doTime(self.moves)
        if not ret[0]:
            return ret

        # Sets unique index on service movement features
        idx = 0
        for f in self.moves:
            f.setProp(FEATPROP.MOVE_INDEX.value, idx)
            idx = idx + 1

        # printFeatures(self.moves, "route")
        # printFeatures([Feature(geometry=asLineString(self.moves))], "route")
        logger.debug(f"generated {len(self.moves)} points")
        return (True, "ServiceMove::move completed")


    def move_loop(self):
        """
        Simulates a vehicle that goes back and forth between the aircraft and a depot
        until all load is loaded/unloaded.
        """
        # Temp disabled
        return (False, "ServiceMove::move_loop currently not usable or not implemented")

        # CHECK: Service has vehicle
        vehicle = self.service.vehicle
        if vehicle is None:
            return (False, "ServiceMove::move_loop: service has no vehicle")

        # CHECK: Vehicle has "capacity"
        if vehicle.max_capacity is None:
            return (False, "ServiceMove::move_loop: service vehicle has no capacity")

        if vehicle.max_capacity == inf:
            return (False, "ServiceMove::move_loop: service vehicle has infinite capacity, we travel once only")

        # CHECK: Service has quantity
        if self.service.quantity is None or self.service.quantity <= 0:
            return (False, "ServiceMove::move_loop: service has no quantity")

        # CHECK: Vehicle or service have "load/unload time" (direct value or computed from capacity + flow)
        # CHECK: Service has speed of service:
        if self.service.flow is None or self.service.quantity <= 0:
            return (False, "ServiceMove::move_loop: service has no service speed (flow)")

        # CHECK: Vehicle or service have "setup/unsetup time" (optional)
        if self.service.setup_time is None:
            logger.debug("forced service setup time to 0")
            self.service.setup_time = 0

        # CHECK: Quantity/capacity does not involve "too many" roundtrips (max ~10)


        # BEGINNING OF LOOP, go to ramp
        #
        speeds = self.service.vehicle.speed

        startpos = self.service.vehicle.getPosition()
        # logger.debug("start position %s" % (startpos))
        service_type = type(self.service).__name__.replace("Service", "").lower()

        startpos.setSpeed(0)  # starts at rest
        startpos.setProp(FEATPROP.MARK.value, SERVICE_PHASE.START.value)
        self.moves.append(startpos)

        # starting position to network
        startnp = self.airport.service_roads.nearest_point_on_edge(startpos)
        if startnp[0] is None:
            logger.warning("no nearest_point_on_edge for startpos")
        else:
            startnp[0].setSpeed(speeds["slow"])  # starts moving
            self.moves.append(startnp[0])

        # logger.debug("start vertex %s" % (startnp[0]))

        startnv = self.airport.service_roads.nearest_vertex(startpos)
        if startnv[0] is None:
            logger.warning("no nearest_vertex for startpos")

        # find ramp position, use ramp center if none is given
        gseprofile = self.service.actype.gseprofile
        if gseprofile is not None:
            status = self.service.ramp.makeServicePOIs(self.service.actype)
            if not status[0]:
                logger.warning(f"create ramp service points failed {gseprofile}")
            else:
                logger.debug(f"created ramp service points {list(gseprofile['services'].keys())}")

        ramp_stop = self.service.ramp.getServicePOI(service_type, self.service.actype)

        if ramp_stop is None:
            logger.warning(f"failed to find ramp stop for { service_type }, using ramp center")
            ramp_stop = self.service.ramp  # use center of ramp

        if ramp_stop is None:
            logger.warning(f"failed to find ramp stop and/or center for { service_type }")
            return (False, "ServiceMove:move: failed to find ramp stop")

        # logger.debug("ramp %s" % (ramp_stop))

        # find closest point on network to ramp
        ramp_npe = self.airport.service_roads.nearest_point_on_edge(ramp_stop)
        if ramp_npe[0] is None:
            logger.warning("no nearest_point_on_edge for ramp_stop")
        ramp_nv = self.airport.service_roads.nearest_vertex(ramp_stop)
        if ramp_nv[0] is None:
            logger.warning("no nearest_vertex for ramp_stop")

        # logger.debug("ramp vertex %s" % (ramp_nv[0]))

        # route from start to ramp
        logger.debug(f"route from start {startnv[0].id} to ramp {ramp_nv[0].id} (vertices)")
        rt1 = Route(self.airport.service_roads, startnv[0].id, ramp_nv[0].id)
        # rt1.find()  # auto route
        # r1 = self.airport.service_roads.Dijkstra(startnv[0].id, ramp_nv[0].id)

        if rt1.found():
            for vtx in rt1.get_vertices():
                # vtx = self.airport.service_roads.get_vertex(vid)
                pos = MovePoint.new(vtx)
                pos.setProp("_serviceroad", vtx.id)
                pos.setSpeed(speeds["normal"])
                self.moves.append(pos)
        else:
            logger.debug(f"no route from start {startnv[0].id} to ramp {ramp_nv[0].id}")

        if ramp_npe[0] is not None:
            ramp_npe[0].setSpeed(speeds["slow"])
            ramp_npe[0].setProp(FEATPROP.MARK.value, SERVICE_PHASE.ARRIVED.value)
            self.moves.append(ramp_npe[0])

        ramp_stop.setSpeed(0)
        ramp_stop.setProp(FEATPROP.MARK.value, SERVICE_PHASE.SERVICE_START.value)
        self.moves.append(ramp_stop)

        self.service.vehicle.setPosition(ramp_stop)

        # Prepare nearest depot
        nearest_depot = self.airport.getNearestServiceDepot(service_type, ramp_stop)
        # CHECK: Service has depot where to load/drop?
        if nearest_depot is None:
            return (False, "ServiceMove::move_loop: service has no depot")
        nd_npe = self.airport.service_roads.nearest_point_on_edge(nearest_depot)
        if nd_npe[0] is None:
                logger.warning("no nearest_point_on_edge for nearest_depot")
        nd_nv = self.airport.service_roads.nearest_vertex(nearest_depot)
        if nd_nv[0] is None:
            logger.warning("no nearest_vertex for nearest_depot")

        # route ramp -> nearest depot
        logger.debug(f"route from ramp {ramp_nv[0].id} to nearest depot {nd_nv[0].id} (vertices)")
        go_unload = Route(self.airport.service_roads, ramp_nv[0].id, nd_nv[0].id)
        if not go_unload.found():
            logger.warning("no route from ramp to nearest depot")
        go_load = Route(self.airport.service_roads, nd_nv[0].id, ramp_nv[0].id)
        if not go_load.found():
            logger.warning("no route from nearest depot to ramp")
        logger.debug("ready to loop")
        vehicle = self.service.vehicle
        service = self.service
        logger.debug(f"vehicle capacity {vehicle.max_capacity}, current load {vehicle.current_load}")

        # Availability on first trip:
        equipment_capacity = vehicle.max_capacity - vehicle.current_load  # may not be empty when it arrives
        # .. servicing ..
        # before service, may first go to ramp rest area.
        # after service, may first go to ramp rest area before leaving ramp.
        #
        # LOOP, go to next position
        while self.service.quantity > 0:
            #
            # Fill vehicle, decrease service quantity
            if vehicle.max_capacity == inf:  # infinite capacity; served in one trip, should not come here...
                vehicle.current_load = service.quantity
                svc_duration = vehicle.service_duration(service.quantity)
                service.quantity = 0
            elif service.quantity < equipment_capacity:  # one last trip
                vehicle.current_load = vehicle.current_load + service.quantity
                svc_duration = vehicle.service_duration(service.quantity)
                logger.debug(f"loaded {service.quantity}, 0 remaining")
                service.quantity = 0
            else:
                logger.debug(f"loaded {equipment_capacity}, {service.quantity - equipment_capacity} remaining")
                vehicle.current_load = vehicle.max_capacity
                svc_duration = vehicle.service_duration(vehicle.max_capacity)
                service.quantity = service.quantity - equipment_capacity

            logger.debug(f"loaded {equipment_capacity}, {service.quantity - equipment_capacity} remaining, load duration={svc_duration}")
            ramp_stop.setPause(svc_duration)

            # go to nearest depot
            # ramp->network edge
            pos = MovePoint.new(ramp_npe[0])
            pos.setSpeed(speeds["slow"])
            self.moves.append(pos)
            # network edge->network vertex
            pos = MovePoint.new(nd_nv[0])
            pos.setProp("_serviceroad", nd_nv[0].id)
            pos.setSpeed(speeds["slow"])
            self.moves.append(pos)
            # network vertex->network vertex
            if go_unload.found():
                for vtx in go_unload.get_vertices():
                    # vtx = self.airport.service_roads.get_vertex(vid)
                    pos = MovePoint.new(vtx)
                    pos.setProp("_serviceroad", vtx.id)
                    pos.setSpeed(speeds["normal"])
                    self.moves.append(pos)
            else:
                logger.debug(f"no route from ramp {ramp_nv[0].id} to nearest depot {nd_nv[0].id}")
            # network vertex->network edge (close to depot)
            pos = MovePoint.new(nd_npe[0])
            pos.setSpeed(speeds["slow"])
            self.moves.append(pos)
            # network edge-> depot
            pos = MovePoint.new(nearest_depot)
            pos.setSpeed(speeds["slow"])
            self.moves.append(pos)

            #
            # Empty vehicle
            vehicle.setPosition(pos)
            svc_duration = vehicle.service_duration(vehicle.current_load)
            logger.debug(f"unloaded {vehicle.current_load}, {service.quantity} remaining, unload duration={svc_duration}")
            pos.setPause(svc_duration)

            vehicle.current_load = 0
            equipment_capacity = vehicle.max_capacity

            # go back to ramp
            # depot ->network edge (close to depot)
            pos = MovePoint.new(nd_npe[0])
            pos.setSpeed(speeds["slow"])
            self.moves.append(pos)
            # network edge->network vertex (close to depot)
            pos = MovePoint.new(nd_nv[0])
            pos.setSpeed(speeds["slow"])
            self.moves.append(pos)
            # network vertex->network vertex
            if go_load.found():
                for vtx in go_load.get_vertices():
                    # vtx = self.airport.service_roads.get_vertex(vid)
                    pos = MovePoint.new(vtx)
                    pos.setProp("_serviceroad", vtx.id)
                    pos.setSpeed(speeds["normal"])
                    self.moves.append(pos)
            else:
                logger.debug(f"no route from nearest depot {nd_nv[0].id} to ramp {ramp_nv[0].id}")
            # ramp->network edge
            pos = MovePoint.new(ramp_npe[0])
            pos.setSpeed(speeds["slow"])
            self.moves.append(pos)
            # network edge->ramp
            pos = MovePoint.new(ramp_stop)
            pos.setSpeed(speeds["slow"])
            self.moves.append(pos)


        # END OF LOOP, go to next position
        #
        # find end position if none is given
        finalpos = self.service.vehicle.next_position
        if finalpos is None:
            finalpos = self.airport.selectRandomServiceRestArea(service_type)
            # logger.debug(f"end position { finalpos }")

            if finalpos is None:
                logger.warning(f"no end rest area for { service_type }, using start position")
                finalpos = startpos


        # find end position on network
        endnp = self.airport.service_roads.nearest_point_on_edge(finalpos)
        if endnp[0] is None:
            logger.warning("no nearest_point_on_edge for end")

        endnv = self.airport.service_roads.nearest_vertex(finalpos)
        if endnv[0] is None:
            logger.warning("no nearest_vertex for end")

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

        logger.debug(f"route from {ramp_nv[0].id} to {endnv[0].id}")
        r2 = Route(self.airport.service_roads, ramp_nv[0].id, endnv[0].id)
        if r2.found():
            for vtx in r2.get_vertices():
                pos = MovePoint.new(vtx)
                pos.setProp("_serviceroad", vtx.id)
                pos.setSpeed(speeds["normal"])
                self.moves.append(pos)
        else:
            logger.debug(f"no route from ramp {ramp_nv[0].id} to end {endnv[0].id}")

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

        logger.debug(f"generated {len(self.moves)} points")
        return (False, "ServiceMove::make not implemented")

