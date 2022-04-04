#  Python classes to format features for output to different channel requirements
#
import logging
import datetime
import json

from ..constants import FEATPROP
from ..airport import Airport

from .format import Formatter

logger = logging.getLogger("ADSBFormatter")


class ADSBFormatter(Formatter):

    FILE_EXTENTION = "csv"

    def __init__(self, feature: "FeatureWithProps"):
        Formatter.__init__(self, feature=feature)
        self.name = "adsb"
