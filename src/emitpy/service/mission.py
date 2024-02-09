"""
A Mission is a trip of a vehicle around the airport through a list of checkpoints.
"""
import logging
from datetime import datetime

from emitpy.constants import FEATPROP, REDIS_DATABASE, ID_SEP, key_path
from emitpy.geo import FeatureWithProps
from .ground_support import GroundSupport


logger = logging.getLogger("Mission")


class Mission(GroundSupport):
    def __init__(self, operator: "Company", checkpoints: [str], name: str):
        GroundSupport.__init__(self, operator=operator)
        self.checkpoints = checkpoints
        # Avoid ID_SEP characters in mission name
        self.mission = f"{name.replace(ID_SEP, '-')}-{datetime.now().strftime('%y%j-%f')}"  # -{round(random.random()*10000):05}
        self.checkpoint_control_time = 120  # seconds, could be a param

    @staticmethod
    def getCombo():
        """
        Gets a list of (code, description) pairs for mission types.
        """
        a = []
        a.append(("security", "Security"))
        a.append(("emergency", "Emergency"))
        a.append(("fire", "Fire"))
        a.append(("police", "Police"))
        return a

    def getId(self):
        """
        Return a mission identifier built from a user-supplied string constant and date-based numbers,
        almost random with milliseconds.
        """
        return self.mission

    def getInfo(self):
        return {
            "ground-support": super().getInfo(),  # contains PTS, etc.
            "mission-identifier": self.getId(),
            "operator": self.operator.getInfo(),
            "vehicle": self.vehicle.getInfo(),
            "icao24": self.vehicle.icao24,
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
        return checkpoint.getProp(FEATPROP.CONTROL_TIME, dflt=self.checkpoint_control_time)
