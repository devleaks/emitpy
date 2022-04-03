#  Python classes to format features for output to different channel requirements
#
import logging
import datetime
import json

from ..constants import FEATPROP
from ..airport import Airport

from .format import Formatter

logger = logging.getLogger("ADS-B")


class Viewer(Formatter):

    FILE_EXTENTION = "csv"

    def __init__(self, feature: "FeatureWithProps"):
        Formatter.__init__(self, feature=feature)
        # rename a few properties for viewer:
        self.setProp("classId") = "aircrafts"
        self.setProp("typeId") = "AIRCRAFT"
        self.setProp("orgId") = self.getProp("airline.name")
        self.setProp("group_name") = "AIRCRAFTS"
        self.setProp("status") = "ACTIVE"


    def __str__(self):
        # viewer message for positions of things (aircraft, vehicle)
        return json.dumps({
            "source": "emitpy",
            "topic": "gps/aircrafts",
            "type": "map",
            "data": self
        })
