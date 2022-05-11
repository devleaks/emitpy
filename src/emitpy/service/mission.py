"""
A Mission is a trip of a vehicle around the airport through a list of checkpoints.
"""
import sys
import logging
import random
from datetime import datetime

from emitpy.constants import FEATPROP, REDIS_DATABASE
from .service import GroundSupport
from .servicevehicle import ServiceVehicle
from emitpy.geo import FeatureWithProps


logger = logging.getLogger("Mission")


class Mission(GroundSupport):

    def __init__(self, operator: "Company", checkpoints: [str], name: str):
        GroundSupport.__init__(self, operator=operator)
        self.checkpoints = checkpoints
        self.mission = f"{name}-{datetime.now().strftime('%y%j-%f')}"  # -{round(random.random()*10000):05}
        self.checkpoint_control_time = 120  # seconds, could be a param

    @staticmethod
    def getCombo():
        """
        Gets a list of (code, description) pairs for mission types.
        """
        a = []
        a.append(("security", "Security"))
        # a.append(("emergency", "Emergency"))
        # a.append(("fire", "Fire"))
        return a


    @staticmethod
    def getHandlers():
        return [
            ("QAS", "Qatar Airport Security"),
            ("QAFD", "Qatar Airport Fire Department"),
            ("QAPD", "Qatar Airport Police Department")
        ]


    def getId(self):
        """
        Return a mission identifier built from a user-supplied string constant and date-based numbers,
        almost random with milliseconds.
        """
        return self.mission


    def getInfo(self):
        return {
            "operator": self.operator.getInfo(),
            "mission": self.mission,
            "vehicle": self.vehicle.getInfo(),
            "icao24": self.vehicle.icao24
        }


    def getKey(self):
        return key_path(REDIS_DATABASE.MISSIONS.value, self.getId())


    def __str__(self):
        s = type(self).__name__


    def addCheckpoint(self, checkpoint: str):
        self.checkpoints.append(checkpoint)


    def duration(self, checkpoint: FeatureWithProps = None):
        """
        Returns mission duration (in minutes) for supplied checkpoint identifier.
        Control at checkpoint can have a variable control duration.

        :param      name:  The name
        :type       name:  str
        """
        if checkpoint is None:
            return self.checkpoint_control_time
        control_time = checkpoint.getProp(FEATPROP.CONTROL_TIME.value)
        if control_time is None:
            return self.checkpoint_control_time  # default
        return control_time
