#  Python classes to format features for Xavier Olive Traffic python package
#
import logging
import json
from jsonpath import JSONPath

from emitpy.constants import FEATPROP
from emitpy.utils import FT, NAUTICAL_MILE

from .formatter import FormatterBase

logger = logging.getLogger("AITFCFormatter")


class TrafficFormatter(FormatterBase):

    NAME = "traffic-flight"

    def __init__(self, feature: "FeatureWithProps"):
        FormatterBase.__init__(self, name=TrafficFormatter.NAME, feature=feature)
        self.name = "lt"

    def __str__(self):
        # {
        #   "timestamp": 1527693698000,
        #   "icao24": "484506",
        #   "latitude": 52.3239704714,
        #   "longitude": 4.7394234794,
        #   "groundspeed": 155,
        #   "track": 3,
        #   "vertical_rate": 2240,
        #   "callsign": "TRA051",
        #   "altitude": 224
        # }

        def getprop(path: str):
            r = JSONPath(path).parse(self.feature.properties)
            if len(r) == 1:
                return r[0]
            if len(r) > 1:
                logger.warning(f":__str__: ambiguous return value for {path}")
                return r[0]
            return None

        f = self.feature

        icao24x = f.getProp(FEATPROP.ICAO24.value)


        coords   = f.coords()

        alt      = f.altitude(0) / FT  # m -> ft

        vspeed   = f.vspeed(0) * FT * 60  # m/s -> ft/min
        speed    = f.speed(0) * 3.6 / NAUTICAL_MILE  # m/s in kn

        emit_type = getprop("$.emit.emit-type")

        if emit_type == "flight":
            callsign = getprop("$.flight.callsign").replace(" ","").replace("-","")
            tailnumber = getprop("$.flight.aircraft.acreg")
        else:  # not a flight
            callsign = getprop("$.service.callsign").replace(" ","").replace("-","")
            tailnumber = getprop("$.vehicle.icao")

        ts = f.getProp(FEATPROP.EMIT_ABS_TIME.value)
        #
        ret = {
          "timestamp": ts,
          "icao24": icao24x,
          "latitude": coords[1],
          "longitude": coords[0],
          "groundspeed": speed,
          "vertical_rate": vspeed,
          "callsign": callsign,
          "tailnumber": tailnumber,
          "altitude": alt
        }
        return json.dumps(ret)


    @staticmethod
    def getAbsoluteTime(f):
        """
        Method that returns the absolute emission time of a formatted message

        :param      f:    { parameter_description }
        :type       f:    { type_description }
        """
        return f["timestamp"]

