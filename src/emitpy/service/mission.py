"""
A Mission is a trip of a vehicle around the airport through a list of checkpoints.
"""
import sys
import logging
import random
from datetime import datetime

from .servicevehicle import ServiceVehicle
from ..geo import FeatureWithProps
from ..graph import Route

logger = logging.getLogger("Service")


class Mission:

    def __init__(self, operator: "Company", checkpoints: [FeatureWithProps]):
        self.operator = operator
        self.checkpoints = checkpoints
        self.mission = f"mission-{round(random.random()*10000):d}"
        self.schedule = None      # scheduled service date/time in minutes after/before(negative) on-block
        self.vehicle = None
        self.starttime = None
        self.route = []
        self.checkpoint_control_time = 120  # seconds

    def getId(self):
        return self.mission


    def getInfo(self):
        return {
            "operator": self.operator.getInfo(),
            "mission": self.mission,
            "vehicle": self.vehicle.getInfo(),
            "icao24": self.vehicle.icao24,
            "ident": self.vehicle.registration
        }


    def __str__(self):
        s = type(self).__name__


    def setVehicle(self, vehicle: ServiceVehicle):
        self.vehicle = vehicle


    def addCheckpoint(self, checkpoint: FeatureWithProps):
        self.checkpoints.append(checkpoint)

    def missionDuration(self, name: str = None):
        """
        Returns mission duration (in minutes) for supplied checkpoint identifier.
        Control at checkpoint can have a variable control duration.

        :param      name:  The name
        :type       name:  str
        """
        return self.checkpoint_control_time

    def run(self):
        return (False, "Mission::run not implemented")

