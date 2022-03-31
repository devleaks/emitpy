#  Python classes to format features for output to different channel requirements
#
import logging
import datetime
import json

from ..constants import FEATPROP
from ..airport import Airport

from .format import Formatter

logger = logging.getLogger("ADS-B")


class ADSB(Formatter):

    FILE_EXTENTION = "csv"

    def __init__(self, feature: "FeatureWithProps"):
        Formatter.__init__(self, feature=feature)

    def __str__(self):
        return json.dumps(self.feature)
