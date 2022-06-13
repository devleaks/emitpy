#  Python classes to format features for output to different channel requirements
#
import logging
import datetime
import json

from emitpy.constants import FEATPROP
from emitpy.airport import Airport

from .formatter import FormatterBase

logger = logging.getLogger("ADSBFormatter")


class ADSBFormatter(FormatterBase):

    def __init__(self, feature: "FeatureWithProps"):
        FormatterBase.__init__(self, "adsb", feature=feature)
        self.fileformat = "csv"