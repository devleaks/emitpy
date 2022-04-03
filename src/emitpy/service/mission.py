"""
A Mission is a trip of a vehicle around the airport through a list of checkpoints.
"""
import sys
import logging
import random
from datetime import datetime

from .servicevehicle import ServiceVehicle
from ..geo import FeatureWithProps, printFeatures, asLineString
from ..graph import Route

logger = logging.getLogger("Service")


class Mission:

    def __init__(self, operator: "Company", checkpoints: [FeatureWithProps]):
        self.operator = operator
        self.checkpoints = checkpoints
        self.mission = "some id"
        self.schedule = None      # scheduled service date/time in minutes after/before(negative) on-block
        self.vehicle = None
        self.starttime = None
        self.route = []

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


    def run(self, moment: datetime):
        if len(self.route) == 0:
            logger.warning(f":run: {type(self).__name__}: no movement")
            return (False, "Service::run no vehicle")
        self.starttime = moment
        return (False, "Service::run not implemented")

