#  Python classes to format features for LiveTraffic XPPlanes
#  See https://github.com/TwinFan/XPPlanes
#
import logging
import json
from jsonpath import JSONPath

from emitpy.constants import FEATPROP
from emitpy.utils import FT, NAUTICAL_MILE

from .formatter import FormatterBase

logger = logging.getLogger("XPPlanes")


class XPPlanesFormatter(FormatterBase):

    NAME = "xpplanes"

    def __init__(self, feature: "FeatureWithProps"):
        FormatterBase.__init__(self, name=XPPlanesFormatter.NAME, feature=feature)
        self.name = "lt"

    def __str__(self):
        # {
        #   "id" : 4711,
        #   "ident" : {
        #     "airline" : "DLH",
        #     "reg" : "D-EVEL",
        #     "call" : "DLH1234",
        #     "label" : "Test Flight"
        #   },
        #   "type" : {
        #     "icao" : "C172",
        #     "wingSpan" : 11.1,
        #     "wingArea" : 16.2
        #   },
        #   "position" : {
        #     "lat" : 51.406292,
        #     "lon" : 6.939847,
        #     "alt_geo" : 407,
        #     "gnd" : true,
        #     "timestamp" : -0.7
        #   },
        #   "attitude" : {
        #     "roll" : -0.2,
        #     "heading" : 42,
        #     "pitch" : 0.1
        #   },
        #   "config" : {
        #     "mass" : 1037.6,
        #     "lift" : 10178.86,
        #     "gear" : 1,
        #     "noseWheel" : -2.5,
        #     "flaps" : 0.5,
        #     "spoiler" : 0
        #   },
        #   "light" : {
        #     "taxi" : true,
        #     "landing" : false,
        #     "beacon" : true,
        #     "strobe" : false,
        #     "nav" : true
        #   }
        # }
        #
        #
        # Field   Description
        #
        # id  Mandatory numeric identification of the plane. Can be a numeric integer value like 4711 or a string value. A string value is interpreted as a hex number, like "00c01abc".
        # ident/  Optional object with plane identifiers, recommended to be sent at least with the first record, but can be updated any time
        # /airline    String used as operator code in CSL model matching
        # /reg    String used as special livery in CSL model matching
        # /call   String used for computing a default label
        # /label  String directly determining the label
        # type/   Optional object with plane type information, recommended to be sent at least with the first record, but can be updated any time
        # /icao   ICAO aircraft type designator used in CSL model matching, defaults to A320
        # /wingSpan   Wing span in meters, used for wake turbulence configuration
        # /wingArea   Wing area in square meters, used for wake turbulence configuration
        # positions/  Mandatory object with position information
        # /lat    latitude, float with decimal coordinates
        # /lon    longitude, float with decimal coordinates
        # /alt_geo    geometric altitude in feet, integer, optional/ignored if gnd = true.
        # /gnd    boolean value stating if plane is on the ground, optional, defaults to false
        # Means: Either gnd = true or alt_geo is required.
        # /timestamp  timestamp, either a float with a relative timestamp in seconds, a float with a Unix epoch timestamp including decimals, or an integer with a Java epoch timestamp (ie. a Unix epoch timestamp in milliseconds). See section Timestamp for more details.
        # attitude/   Optional object with plane attitude information
        # /roll   roll in degrees, float, negative is left
        # /heading    heading in degrees, integer 0 .. 359
        # /pitch  pitch in degrees, float, negative is down
        # config/ Optional object with plane configuration data (unlike type/ this is data which is likely to change throughout a flight)
        # /mass   mass of the plane in kg, used for wake turbulence configuration
        # /lift   current lift in Newton, optional, defaults to mass * earth gravity, used for wake turbulence configuration
        # /gear   gear extension, float 0.0 .. 1.0 with 1.0 fully extended
        # /noseWheel  direction of nose wheel in degrees, float, negative is left, 0.0 straight ahead
        # /flaps  flap extension, float 0.0 .. 1.0 with 1.0 fully extended
        # /spoiler    spoiler extension, float 0.0 .. 1.0 with 1.0 fully extended
        # light/  Optional object with a set of boolean values for the plane's lights
        # /taxi   taxi light
        # /landing    landing lights
        # /beacon beacon light
        # /strobe strobe lights
        # /nav    navigation lights
        #
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

        airline = getprop("$.flight.airline.name")  # IATA name, QR
        label = getprop("$.flight.identifier")
        actype = getprop("$.flight.aircraft.actype.base-type.actype")
        ts = f.getProp(FEATPROP.EMIT_ABS_TIME.value)

        emit_type = getprop("$.emit.emit-type")

        if emit_type == "flight":
            callsign = getprop("$.flight.callsign")
            if callsign is not None:
                callsign = callsign.replace(" ","").replace("-","")
            tailnumber = getprop("$.flight.aircraft.acreg")
        else:  # not a flight
            callsign = getprop("$.vehicle.callsign")
            if callsign is not None:
                callsign = callsign.replace(" ","").replace("-","")
            tailnumber = getprop("$.vehicle.registration")

        ret = {
            "id" : icao24x,
            "ident" : {
                "airline" : airline,
                "reg" : tailnumber,
                "call" : callsign,
                "label" : label
            },
            "type" : {
                # "wingSpan" : 11.1,
                # "wingArea" : 16.2,
                "icao" : actype
            },
            "position" : {
                "lat" : coords[1],
                "lon" : coords[0],
                "alt_geo" : alt,
            #    "timestamp" : ts,
                "gnd" : alt == 0
            },
            # "attitude" : {
            #     "roll" : -0.2,
            #     "heading" : 42,
            #     "pitch" : 0.1
            # },
            # "config" : {
            #     "mass" : 1037.6,
            #     "lift" : 10178.86,
            #     "gear" : 1,
            #     "noseWheel" : -2.5,
            #     "flaps" : 0.5,
            #     "spoiler" : 0
            #     },
            "light" : {
            #     "taxi" : True,
            #     "landing" : False,
                "beacon" : True,
            #     "nav" : True,
                "strobe" : True
            }
        }
        return json.dumps(ret)


    @staticmethod
    def getAbsoluteTime(f):
        """
        Method that returns the absolute emission time of a formatted message

        :param      f:    { parameter_description }
        :type       f:    { type_description }
        """
        return None

