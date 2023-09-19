"""
Build movement of a equipment
"""
import logging
from math import inf


from geojson import Feature

from emitpy.airport import ManagedAirportBase
from emitpy.geo import MovePoint, printFeatures, asLineString
from emitpy.service import Service
from emitpy.graph import Route
from emitpy.constants import FEATPROP, SERVICE_PHASE, MOVE_TYPE
from emitpy.message import ServiceMessage
from .ground_support_movement import GroundSupportMovement

logger = logging.getLogger("ServiceMovement")

MOVE_LOOP = []  # "BaggageService","cargo"


class ServiceMovement(GroundSupportMovement):
    """
    Movement build the detailed path of the aircraft, both on the ground (taxi) and in the air,
    from takeoff to landing and roll out.
    """
    def __init__(self, service: Service, airport: ManagedAirportBase):
        GroundSupportMovement.__init__(self, airport=airport, reason=service)
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

    def no_drive(self):
        """
        No movement associated with this service, just emit ServiceMessage at event time.
        Since there is no movement associated, there is no sync label to be used.
        So the relative time will be relative to the supplied scheduled time, which normally is ONBLOCK/OFFBLOCK time.
        """
        duration = self.service.duration()
        if duration == 0:
            self.addMessage(ServiceMessage(subject=f"«{self.service.label}» {SERVICE_PHASE.OCCURRED.value}",
                                           service=self,
                                           sync=SERVICE_PHASE.START.value,
                                           info=self.getInfo()))
            logger.debug(f"{self.service.name} added 1 message")
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
                                           relative_time=(duration)))
            logger.debug(f"{self.service.name} added 2 messages")

    def drive(self):
        # Special case 1: Service "event reporting only", no move
        if self.service.vehicle is None:  # Service with no vehicle movement
            logger.debug(f"service {type(self.service).__name__} «{self.service.label}» has no vehicle, assuming event report only")
            self.no_drive()
            logger.debug(f"generated {len(self.getMovePoints())} points")
            return (True, "ServiceMovement::drive: no moves, assuming event report only")

        # Special case 2: Service vehicle going back and forth between ramp and depot
        # if type(self.service).__name__ in MOVE_LOOP:
        if self.service.using_quantity() and self.service.vehicle is not None and self.service.vehicle.has_capacity():
            logger.debug(f"moving loop for {self.service.getId()}..")
            ret = self.drive_loop()
            if ret[0]:
                return ret
            logger.warning("!!!!!!!!!!!" + ret[1])
            logger.debug(f"..loop did not complete successfully, using normal move..")

        # Normal case:
        move_points = self.getMovePoints()
        speeds = self.service.vehicle.speed

        startpos = self.service.vehicle.getPosition()
        if startpos is None:
            logger.warning(f"no start position for {self.service.vehicle.getId()}")
        service_type = type(self.service).__name__.replace("Service", "").lower()

        startpos.setSpeed(0)  # starts at rest
        startpos.setMark(SERVICE_PHASE.START.value)
        move_points.append(startpos)

        logger.debug(f"At start position.")
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
            move_points.append(startnp[0])

        logger.debug(f"Leaving start position..")
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

        service_pos = self.service.ramp.getServicePOI(service_type, self.service.actype)
        svc_end = service_pos.copy()

        wer = service_type
        if service_pos is None:
            logger.warning(f"failed to find ramp stop for { self.service.actype.typeId }, { service_type }, using ramp center")
            service_pos = self.service.ramp  # use center of ramp
            wer = "center"

        if service_pos is None:
            logger.warning(f"failed to find ramp stop and/or center for { service_type }")
            return (False, ":move: failed to find ramp stop")

        # logger.debug("ramp %s" % (service_pos))

        # find closest point on network to ramp
        ramp_npe = self.airport.service_roads.nearest_point_on_edge(service_pos)
        if ramp_npe[0] is None:
            logger.warning(f"no nearest_point_on_edge for service_pos ({wer})")
        ramp_nv = self.airport.service_roads.nearest_vertex(service_pos)
        if ramp_nv[0] is None:
            logger.warning(f"no nearest_vertex for service_pos ({wer})")

        # logger.debug("ramp vertex %s" % (ramp_nv[0]))

        # route from start to ramp
        logger.debug(f"..route from start {startnv[0].id} to ramp/{wer} {ramp_nv[0].id} (vertices)..")
        rt1 = Route(self.airport.service_roads, startnv[0].id, ramp_nv[0].id)
        # rt1.find()  # auto route
        # r1 = self.airport.service_roads.Dijkstra(startnv[0].id, ramp_nv[0].id)

        if rt1.found():
            for vtx in rt1.get_vertices():
                # vtx = self.airport.service_roads.get_vertex(vid)
                pos = MovePoint.new(vtx)
                pos.setProp("_serviceroad", vtx.id)
                pos.setSpeed(speeds["normal"])
                move_points.append(pos)
        else:
            logger.debug(f"no route from start {startnv[0].id} to ramp {ramp_nv[0].id}")

        # Phases ARRIVED / LEAVE is relative to the RAMP, not the service position
        if ramp_npe[0] is not None:
            ramp_npe[0].setSpeed(speeds["slow"])
            ramp_npe[0].setMark(SERVICE_PHASE.ARRIVED.value)
            move_points.append(ramp_npe[0])
            self.addMessage(ServiceMessage(subject=f"{self.service.vehicle.icao24} {SERVICE_PHASE.ARRIVED.value}",
                                           service=self,
                                           sync=SERVICE_PHASE.ARRIVED.value,
                                           info=self.getInfo()))
        else:
            logger.warning(f"could not find ramp_npe (arriving)")

        logger.debug(f"..reached ramp..")
        # ###
        # If there is a stop poi named "STANDBY" and if the service has pause_before > 0
        # we first go to the standby position and wait pause_before minutes.
        #
        # before service, may first go to ramp rest area.
        ramp_standby = self.service.ramp.getServicePOI("standby", self.service.actype)
        logger.debug(f"..stand-by?..")
        if ramp_standby is not None and self.service.pause_before > 0:
            ramp_standby_pos = MovePoint.new(ramp_standby)
            ramp_standby_pos.setSpeed(0)
            ramp_standby_pos.setMark("standby-before-service")
            ramp_standby_pos.setPause(self.service.pause_before)
            move_points.append(ramp_standby_pos)
            logger.debug(f"added pause {self.service.pause_before}m before service")
        else:
            logger.debug(f"..(no standby before service)..")

        service_pos.setSpeed(0)  # service_pos should have orientation set
        service_pos.setMark(SERVICE_PHASE.SERVICE_START.value)
        logger.debug(f"..reached service position..")

        # .. servicing ..
        service_duration = self.service.duration(add_setup=True)
        service_pos.setPause(service_duration)
        logger.debug(f"..serving (service duration {service_duration} secs)..")
        move_points.append(service_pos)
        self.service.vehicle.setPosition(service_pos)
        # to be correct, service will start after setup_time...
        reltime = 0
        if self.service.vehicle.setup_time is not None:
            reltime = self.service.vehicle.setup_time
        self.addMessage(ServiceMessage(subject=f"Service {self.getId()} has started",
                                       service=self,
                                       sync=SERVICE_PHASE.SERVICE_START.value,
                                       relative_time=reltime,
                                       info=self.getInfo()))

        # service terminated
        # svc_end is service_pos.copy()
        logger.debug(f"..leaving service position..")
        svc_end.setSpeed(0)
        svc_end.setMark(SERVICE_PHASE.SERVICE_END.value)
        move_points.append(svc_end)

        # to be correct, service will end before cleanup_time...
        reltime = 0
        if self.service.vehicle.cleanup_time is not None:
            reltime = - self.service.vehicle.cleanup_time
        self.addMessage(ServiceMessage(subject=f"Service {self.getId()} has ended",
                                       service=self,
                                       sync=SERVICE_PHASE.SERVICE_END.value,
                                       relative_time=reltime,
                                       info=self.getInfo()))
        # ###
        # If there is a stop poi named "REST" and if the service has pause_after > 0
        # we first go to the rest position and wait pause_after minutes.
        #
        # after service, may first go to ramp rest area before leaving ramp.
        logger.debug(f"..resting close by?..")
        ramp_rest = self.service.ramp.getServicePOI("standby", self.service.actype)
        if ramp_rest is not None and self.service.pause_after > 0:
            ramp_rest_pos = MovePoint.new(ramp_rest)
            ramp_rest_pos.setSpeed(0)
            ramp_rest_pos.setMark("rest-after-service")
            ramp_rest_pos.setPause(self.service.pause_after)
            move_points.append(ramp_standby_pos)
            logger.debug(f"added pause {self.service.pause_after}m after service")
        else:
            logger.debug(f"..(no pause after, leaving ramp)..")

        if ramp_npe[0] is not None:
            ramp_leave = ramp_npe[0].copy()
            ramp_leave.setSpeed(speeds["slow"])
            ramp_leave.setMark(SERVICE_PHASE.LEAVE.value)
            move_points.append(ramp_leave)
            self.addMessage(ServiceMessage(subject=f"{self.service.vehicle.icao24} {SERVICE_PHASE.LEAVE.value}",
                                           service=self,
                                           sync=SERVICE_PHASE.LEAVE.value,
                                           info=self.getInfo()))
        else:
            logger.warning(f"could not find ramp_npe (leaving)")

        logger.debug(f"..leaving ramp..")

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

        # route ramp to end position
        logger.debug(f"..route from {ramp_nv[0].id} to {endnv[0].id}..")
        r2 = Route(self.airport.service_roads, ramp_nv[0].id, endnv[0].id)
        if r2.found():
            for vtx in r2.get_vertices():
                pos = MovePoint.new(vtx)
                pos.setProp("_serviceroad", vtx.id)
                pos.setSpeed(speeds["normal"])
                move_points.append(pos)
            logger.debug(f"..travelling to next position..")
        else:
            logger.debug(f"no route from ramp {ramp_nv[0].id} to end {endnv[0].id}")

        if endnp is not None:
            endnp[0].setSpeed(speeds["slow"])
            move_points.append(endnp[0])
            logger.debug(f"..closing to next position..")

        if finalpos == startpos:
            finalpos = finalpos.copy()  # in case same as start...

        finalpos.setSpeed(0)
        finalpos.setMark(SERVICE_PHASE.END.value)
        move_points.append(finalpos)
        self.service.vehicle.setPosition(finalpos)
        logger.debug(f"..parked at next position")

        self.addMessage(ServiceMessage(subject=f"{self.service.vehicle.icao24} {SERVICE_PHASE.END.value}",
                                       service=self,
                                       sync=SERVICE_PHASE.END.value,
                                       info=self.getInfo()))

        # Sets unique index on service movement features
        idx = 0
        for f in self.getMovePoints():
            f.setProp(FEATPROP.MOVE_INDEX.value, idx)
            idx = idx + 1

        # printFeatures(self.getMovePoints(), "route")
        # printFeatures([Feature(geometry=asLineString(self.getMovePoints()))], "route")
        logger.debug(f"generated {len(self.getMovePoints())} points")
        return (True, "ServiceMovement::move completed")


    def drive_loop(self):
        """
        Simulates a vehicle that goes back and forth between the aircraft and a depot
        until all load is loaded/unloaded.
        """
        # Temp disabled
        # return (False, "ServiceMovement::drive_loop currently not usable or not implemented")
        MAX_ROUNDTRIPS = 4
        move_points = self.getMovePoints()
        service = self.service
        vehicle = service.vehicle

        # CHECK: Service has vehicle
        if vehicle is None:
            return (False, "ServiceMovement::drive_loop: service has no vehicle")

        # CHECK: Vehicle has "capacity"
        if vehicle.capacity is None:
            return (False, "ServiceMovement::drive_loop: service vehicle has no capacity")

        if vehicle.capacity == inf:
            return (False, "ServiceMovement::drive_loop: service vehicle has infinite capacity, we travel once only")

        # CHECK: Service has quantity
        if service.quantity is None or self.service.quantity == 0:
            return (False, "ServiceMovement::drive_loop: service has no quantity")

        # CHECK: Vehicle or service have "load/unload time" (direct value or computed from capacity + flow)
        # CHECK: Service has speed of service:
        if vehicle.flow is None:
            return (False, "ServiceMovement::drive_loop: vehicle has no service speed (flow)")

        # # CHECK: Vehicle or service have "setup/unsetup time" (optional)
        # if service.setup_time is None:
        #     logger.debug("forced service setup time to 0")
        #     self.service.setup_time = 0

        # BEGINNING OF LOOP, go to ramp
        #
        speeds = self.service.vehicle.speed

        startpos = self.service.vehicle.getPosition()
        # logger.debug("start position %s" % (startpos))
        service_type = type(self.service).__name__.replace("Service", "").lower()

        startpos.setSpeed(0)  # starts at rest
        startpos.setMark(SERVICE_PHASE.START.value)
        move_points.append(startpos)
        logger.debug("At start position")

        # starting position to network
        startnp = self.airport.service_roads.nearest_point_on_edge(startpos)
        if startnp[0] is None:
            logger.warning("no nearest_point_on_edge for startpos")
        else:
            startnp[0].setSpeed(speeds["slow"])  # starts moving
            move_points.append(startnp[0])

        logger.debug("Leaving start position..")
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
            return (False, "ServiceMovement:move: failed to find ramp stop")

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
        logger.debug(f"..route from start {startnv[0].id} to ramp {ramp_nv[0].id} (vertices)..")
        rt1 = Route(self.airport.service_roads, startnv[0].id, ramp_nv[0].id)
        # rt1.find()  # auto route
        # r1 = self.airport.service_roads.Dijkstra(startnv[0].id, ramp_nv[0].id)

        if rt1.found():
            for vtx in rt1.get_vertices():
                # vtx = self.airport.service_roads.get_vertex(vid)
                pos = MovePoint.new(vtx)
                pos.setProp("_serviceroad", vtx.id)
                pos.setSpeed(speeds["normal"])
                move_points.append(pos)
        else:
            logger.debug(f"no route from start {startnv[0].id} to ramp {ramp_nv[0].id}")

        if ramp_npe[0] is not None:
            ramp_npe[0].setSpeed(speeds["slow"])
            ramp_npe[0].setMark(SERVICE_PHASE.ARRIVED.value)
            move_points.append(ramp_npe[0])
            self.addMessage(ServiceMessage(subject=f"{self.service.vehicle.icao24} {SERVICE_PHASE.ARRIVED.value}",
                                           service=self,
                                           sync=SERVICE_PHASE.ARRIVED.value,
                                           info=self.getInfo()))
        else:
            logger.warning(f"could not find ramp_npe (arriving)")

        logger.debug(f"..reached ramp..")

        ramp_stop.setSpeed(0)
        ramp_stop.setMark(SERVICE_PHASE.SERVICE_START.value)
        move_points.append(ramp_stop)
        logger.debug(f"..reached service position..")

        self.service.vehicle.setPosition(ramp_stop)

        # before service, may first go to ramp rest area.
        ramp_standby = self.service.ramp.getServicePOI("standby", self.service.actype)
        logger.debug(f"..stand-by?..")
        if ramp_standby is not None and self.service.pause_before > 0:
            ramp_standby_pos = MovePoint.new(ramp_standby)
            ramp_standby_pos.setSpeed(0)
            ramp_standby_pos.setMark("standby-before-service")
            ramp_standby_pos.setPause(self.service.pause_before)
            move_points.append(ramp_standby_pos)
            logger.debug(f"added pause {self.service.pause_before}m before service")
        else:
            logger.debug(f"..(no standby before service)..")

        # Prepare looping
        #
        # Prepare nearest depot
        logger.debug("..preparing for loop..")
        nearest_depot = self.airport.getNearestServiceDepot(service_type, ramp_stop)
        # CHECK: Service has depot where to load/drop?
        if nearest_depot is None:
            return (False, "ServiceMovement::drive_loop: service has no depot")
        nd_npe = self.airport.service_roads.nearest_point_on_edge(nearest_depot)
        if nd_npe[0] is None:
            logger.warning("no nearest_point_on_edge for nearest_depot")
        nd_nv = self.airport.service_roads.nearest_vertex(nearest_depot)
        if nd_nv[0] is None:
            logger.warning("no nearest_vertex for nearest_depot")

        # Prepare route ramp -> nearest depot
        logger.debug(f"route from ramp {ramp_nv[0].id} to nearest depot {nd_nv[0].id} (vertices)")
        go_to_depot = Route(self.airport.service_roads, ramp_nv[0].id, nd_nv[0].id)
        if not go_to_depot.found():
            logger.warning("no route from ramp to nearest depot")
        go_to_ramp = Route(self.airport.service_roads, nd_nv[0].id, ramp_nv[0].id)
        if not go_to_ramp.found():
            logger.warning("no route from nearest depot to ramp")
        #
        # Looping ready
        logger.debug("..loop ready to be used..")

        logger.debug("LOOP STARTED..")
        loading = self.service.quantity > 0
        loadstr = "load" if loading else "unload"
        opploadstr = "unload" if loading else "load"
        unit_left = abs(self.service.quantity)
        logger.debug(f"vehicle capacity {vehicle.capacity}, current load {vehicle.current_load}, quantity {unit_left}, loading={loading}")

        # to be correct, service will start after setup_time...
        reltime = 0
        if vehicle.setup_time is not None:
            reltime = vehicle.setup_time
        self.addMessage(ServiceMessage(subject=f"Service {self.getId()} has started",
                                       service=self,
                                       sync=SERVICE_PHASE.SERVICE_START.value,
                                       relative_time=reltime,
                                       info=self.getInfo()))

        # .. servicing ..
        # before service, may first go to ramp rest area.
        # after service, may first go to ramp rest area before leaving ramp.
        #
        # LOOP, go to next position
        num_roundtrips = 0
        while unit_left > 0 and num_roundtrips < MAX_ROUNDTRIPS:
            #
            # Fill vehicle, decrease service quantity
            if loading:
                done = vehicle.load(quantity=unit_left)
            else:
                done = vehicle.unload(quantity=unit_left)
            this_load_duration = vehicle.service_duration(quantity=done, add_setup=True)
            unit_left = unit_left - done
            this_load = ramp_stop.copy()
            this_load.setPause(this_load_duration)
            logger.debug(f"{loadstr}ed {done}, {unit_left} remaining, load duration={this_load_duration}")

            if unit_left > 0:  # need to go to depot
                logger.debug(f"Going to depot..")
                # go to nearest depot
                # ramp->network edge
                pos = MovePoint.new(ramp_npe[0])
                pos.setMark(None)
                pos.setSpeed(speeds["slow"])
                move_points.append(pos)
                logger.debug(f"..leaving service position..")
                # network edge->network vertex
                pos = MovePoint.new(nd_nv[0])
                pos.setMark(None)
                pos.setProp("_serviceroad", nd_nv[0].id)
                pos.setSpeed(speeds["slow"])
                move_points.append(pos)
                logger.debug(f"..leaving ramp..")
                # network vertex->network vertex
                if go_to_depot.found():
                    for vtx in go_to_depot.get_vertices():
                        # vtx = self.airport.service_roads.get_vertex(vid)
                        pos = MovePoint.new(vtx)
                        pos.setMark(None)
                        pos.setProp("_serviceroad", vtx.id)
                        pos.setSpeed(speeds["normal"])
                        move_points.append(pos)
                    logger.debug(f"..travelling to depot..")
                else:
                    logger.debug(f"no route from ramp {ramp_nv[0].id} to nearest depot {nd_nv[0].id}")
                # network vertex->network edge (close to depot)
                pos = MovePoint.new(nd_npe[0])
                pos.setMark(None)
                pos.setSpeed(speeds["slow"])
                move_points.append(pos)
                logger.debug(f"..approaching depot..")
                # network edge-> depot
                pos = MovePoint.new(nearest_depot)
                pos.setMark(None)
                pos.setSpeed(speeds["slow"])
                move_points.append(pos)
                logger.debug(f"..parking at depot..")
                #
                # Empty or refill vehicle
                vehicle.setPosition(pos)
                if loading:
                    refill = vehicle.unload()
                else:
                    refill = vehicle.load()
                refill_duration = vehicle.service_duration(refill, add_setup=True)
                pos.setPause(refill_duration)
                logger.debug(f"..{opploadstr}ed at depot, duration={refill_duration}..")

                # go back to ramp
                # depot ->network edge (close to depot)
                pos = MovePoint.new(nd_npe[0])
                pos.setMark(None)
                pos.setSpeed(speeds["slow"])
                move_points.append(pos)
                logger.debug(f"..leaving depot parking..")
                # network edge->network vertex (close to depot)
                pos = MovePoint.new(nd_nv[0])
                pos.setMark(None)
                pos.setSpeed(speeds["slow"])
                move_points.append(pos)
                logger.debug(f"..leaving depot..")
                # network vertex->network vertex
                if go_to_ramp.found():
                    for vtx in go_to_ramp.get_vertices():
                        # vtx = self.airport.service_roads.get_vertex(vid)
                        pos = MovePoint.new(vtx)
                        pos.setMark(None)
                        pos.setProp("_serviceroad", vtx.id)
                        pos.setSpeed(speeds["normal"])
                        move_points.append(pos)
                    logger.debug(f"..travelling to ramp..")
                else:
                    logger.debug(f"no route from nearest depot {nd_nv[0].id} to ramp {ramp_nv[0].id}")
                # ramp->network edge
                pos = MovePoint.new(ramp_npe[0])
                pos.setMark(None)
                pos.setSpeed(speeds["slow"])
                move_points.append(pos)
                logger.debug(f"..reached ramp..")
                # network edge->ramp
                pos = MovePoint.new(ramp_stop)
                pos.setMark(None)
                pos.setSpeed(speeds["slow"])
                move_points.append(pos)
                logger.debug(f"..reached service position")
                num_roundtrips = num_roundtrips + 1

        logger.debug(f"..LOOP TERMINATED ({num_roundtrips} round trips)")
        if num_roundtrips > MAX_ROUNDTRIPS:
            logger.warning(f"SERVICE INTERRUMPTED TOO MANY ROUNDTRIPS ({num_roundtrips})")

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
        svc_end.setMark(SERVICE_PHASE.SERVICE_END.value)
        move_points.append(svc_end)
        logger.debug(f"..leaving service position..")

        reltime = 0
        if vehicle.cleanup_time is not None:
            reltime = - vehicle.cleanup_time
        self.addMessage(ServiceMessage(subject=f"Service {self.getId()} has ended",
                                       service=self,
                                       sync=SERVICE_PHASE.SERVICE_END.value,
                                       relative_time=reltime,
                                       info=self.getInfo()))

        # route ramp to end position
        # to be correct, service will end before cleanup_time...
        if ramp_npe[0] is not None:
            ramp_leave = ramp_npe[0].copy()
            ramp_leave.setSpeed(speeds["slow"])
            ramp_leave.setMark(SERVICE_PHASE.LEAVE.value)
            move_points.append(ramp_leave)
            self.addMessage(ServiceMessage(subject=f"{self.service.vehicle.icao24} {SERVICE_PHASE.LEAVE.value}",
                                           service=self,
                                           sync=SERVICE_PHASE.LEAVE.value,
                                           info=self.getInfo()))
            logger.debug(f"..leaving ramp..")

        logger.debug(f"route from {ramp_nv[0].id} to {endnv[0].id}")
        r2 = Route(self.airport.service_roads, ramp_nv[0].id, endnv[0].id)
        if r2.found():
            for vtx in r2.get_vertices():
                pos = MovePoint.new(vtx)
                pos.setProp("_serviceroad", vtx.id)
                pos.setSpeed(speeds["normal"])
                move_points.append(pos)
            logger.debug(f"..travelling to next position..")
        else:
            logger.debug(f"no route from ramp {ramp_nv[0].id} to end {endnv[0].id}")

        if endnp is not None:
            endnp[0].setSpeed(speeds["slow"])
            move_points.append(endnp[0])
            logger.debug(f"..closing to next position..")

        if finalpos == startpos:
            finalpos = finalpos.copy()  # in case same as start...

        finalpos.setSpeed(0)
        finalpos.setMark(SERVICE_PHASE.END.value)
        move_points.append(finalpos)
        logger.debug(f"..parked at next position")
        self.service.vehicle.setPosition(finalpos)

        # Sets unique index on service movement features
        idx = 0
        for f in self.getMovePoints():
            f.setProp(FEATPROP.MOVE_INDEX.value, idx)
            idx = idx + 1

        # printFeatures(self.getMovePoints(), "route")
        # printFeatures([Feature(geometry=asLineString(self.getMovePoints()))], "route")
        logger.debug(f"generated {len(self.getMovePoints())} points")
        return (True, "ServiceMovement::drive_loop completed")
