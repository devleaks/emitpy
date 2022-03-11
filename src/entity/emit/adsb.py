#  Python classes to format features for output to different channel requirements
#
import logging
import datetime
import json

from ..constants import FEATPROP
from ..airport import Airport

from .broadcast import Formatter

logger = logging.getLogger("LiveTraffic")


class ADSB(Formatter):

    FILE_FORMAT = "csv"

    def __init__(self, feature: "FeatureWithProps"):
        Formatter.__init__(self, feature=feature)

    def __str__(self):
        return json.dumps(self.feature)
