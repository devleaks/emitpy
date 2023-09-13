"""
Ground Support Movement abstract clas for Mission Movement and Service Movement
"""
import logging

from emitpy.constants import FEATPROP
from emitpy.utils import compute_time, interpolate, compute_headings
from emitpy.airport import ManagedAirportBase
from emitpy.geo import Movement


logger = logging.getLogger("GroundSupportMovement")


class GroundSupportMovement(Movement):
    """
    Movement build the detailed path of the aircraft, both on the ground (taxi) and in the air,
    from takeoff to landing and roll out.
    """
    def __init__(self, airport: ManagedAirportBase, reason):
        Movement.__init__(self, airport=airport, reason=reason)

    def getId(self):
        return self.reason.getId()

    def getInfo(self):
        return {
            "ident": self.getId(),
        }

    def getSource(self):
        # Abstract class
        return self.reason

    def move(self):
        status = self.drive()
        if not status[0]:
            logger.warning(status[1])
            return status

        move_points = self.getMovePoints()
        if len(move_points) > 0:

            status = interpolate(move_points, "speed")
            if not status[0]:
                logger.warning(status[1])
            if not status[0]:
                logger.warning(status[1])
                return status

            res = compute_headings(move_points)
            if not res[0]:
                logger.warning(status[1])
                return res

            status = compute_time(move_points)
            if not status[0]:
                logger.warning(status[1])
                return status

            for f in self.getMovePoints():  # we save a copy of the movement timing for rescheduling
                f.setProp(FEATPROP.SAVED_TIME.value, f.time())

        else:
            logger.debug("no move points")

        return (True, "GroundSupportMovement::move completed")

    def drive(self):
        return (True, "GroundSupportMovement::drive completed")
