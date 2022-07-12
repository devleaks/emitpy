#  Python classes to format features for output to different channel requirements
#
import logging
import datetime
import json
from jsonpath import JSONPath
import flatdict

from emitpy.constants import FEATPROP
from emitpy.airport import Airport
from emitpy.utils import FT, NAUTICAL_MILE

from .formatter import FormatterBase

logger = logging.getLogger("LiveTrafficFormatter")


class LiveTrafficWeather:

    NAME = "ltw"

    def __init__(self, metar):
        self.fileformat = "json"
        self.metar = metar

    def __str__(self):
        # Sample messages as sent to LiveTraffic >3.0.0
        # {"ICAO": "OTHH","QNH": "1001", "METAR": "OTHH 120700Z 14009KT 9999 FEW025 35/27 Q1001 NOSIG", "NAME": "OTHH"}
        # {"ICAO": "OTBD","QNH": "1001", "METAR": "OTBD 120630Z 10006KT 9999 FEW025 36/28 Q1001 NOSIG", "NAME": "OTBD"}
        weather = {
            "ICAO": self.metar.station_id,
            "QNH": self.metar.pressure("MB"),
            "METAR": self.metar.metarcode,
            "NAME": Airport.findICAO(self.metar.station_id)
        }
        return json.dumps(weather)


class LiveTrafficFormatter(FormatterBase):

    NAME = "lt"

    def __init__(self, feature: "FeatureWithProps"):
        Formatter.__init__(self, name=LiveTrafficFormatter.NAME, feature=feature)
        self.fileformat = "csv"

    def __str__(self):
        # AITFC,hexid   ,lat    ,lon      ,alt  ,vs  ,airborne,hdg,spd,cs     ,type,tail  ,from,to ,timestamp
        # AITFC,11231627,34.9619,-116.6734,31174,1088,1       ,47 ,493,UAL1136,A319,N832UA,LAX ,DEN,1593034598
        # AITFC,11231627,34.9619,-116.6734,31174,1088,1,47,493,UAL1136,A319,N832UA,LAX,DEN,1593034598
        # AITFC,11076458,33.0809,-117.2493,17574,0,1,356,155,N680CA,,,,,1593034599
        # AITFC,11076458,33.0809,-117.2493,17574,0,1,356,155,N680CA,,,,,1593034599
        # AITFC,11054645,33.6459,-116.1544,400,-640,1,198,43,N659AM,A109,N659AM,UDD,,1593034595
        # AITFC,11054645,33.6459,-116.1544,400,-640,1,198,43,N659AM,A109,N659AM,UDD,,1593034595
        # AITFC,10626394,33.2402,-117.4114,6500,-320,1,120,98,N2373Z,C172,N2373Z,SEE,,1593034599
        # AITFC,10626394,33.2402,-117.4114,6500,-320,1,120,98,N2373Z,C172,N2373Z,SEE,,1593034599
        # AITFC,10674098,34.3683,-118.7518,8600,-64,1,296,123,N28431,AA5,N28431,FUL,,1593034599
        # AITFC,10674098,34.3683,-118.7518,8600,-64,1,296,123,N28431,AA5,N28431,FUL,,1593034599
        #
        # fp = dict(flatdict(f.properties))  # we only flatten props

        def getprop(path: str):
            r = JSONPath(path).parse(self.feature.properties)
            if len(r) == 1:
                return r[0]
            elif len(r) > 1:
                logger.warning(f":__str__: ambiguous return value for {path}")
                return r[0]
            return None

        f = self.feature

        icao24x = f.getProp(FEATPROP.ICAO24.value)
        if icao24x is not None:
            icao24 = int(str(icao24x), 16)  # https://stackoverflow.com/questions/46341329/int-cant-convert-non-string-with-explicit-base-when-converting-to-gui
        else:
            icao24 = None

        coords   = f.coords()

        alt      = f.altitude(0) / FT  # m -> ft

        vspeed   = f.vspeed(0) * FT * 60  # m/s -> ft/min
        speed    = f.speed(0) * 3.6 / NAUTICAL_MILE  # m/s in kn
        airborne = (alt > 0 and speed > 20)

        heading  = f.getProp(FEATPROP.HEADING.value)


        emit_type = getprop("$.emit.emit-type")

        if emit_type == "flight":
            actype = getprop("$.flight.aircraft.actype.base-type.actype")  # ICAO A35K
            callsign = getprop("$.flight.callsign").replace(" ","").replace("-","")
            tailnumber = getprop("$.flight.aircraft.acreg")
            aptfrom = getprop("$.flight.departure.icao")     # IATA
            aptto = getprop("$.flight.arrival.icao")  # IATA
        elif emit_type == "service":
            callsign = getprop("$.service.vehicle.callsign").replace(" ","").replace("-","")
            tailnumber = getprop("$.service.vehicle.registration")
            actype = getprop("$.service.vehicle.icao")
            aptfrom = ""
            aptto = ""
        elif emit_type == "mission":
            callsign = getprop("$.mission.vehicle.callsign").replace(" ","").replace("-","")
            tailnumber = getprop("$.mission.vehicle.registration")
            actype = getprop("$.mission.vehicle.icao")
            aptfrom = ""
            aptto = ""
        else:
            logger.warning(f":__str__: invalid emission type {emit_type}")
            return None

        ts = f.getProp(FEATPROP.EMIT_ABS_TIME.value)
        #         0    ,1       ,2          ,3          ,4    ,5       ,6                     ,7                 ,8
        #         AITFC,hexid   ,lat        ,lon        ,alt  ,vs      ,airborne              ,hdg               ,spd ### ,cs,type,tail,from,to,timestamp
        part1 = f"AITFC,{icao24},{coords[1]},{coords[0]},{alt},{vspeed},{1 if airborne else 0},{round(heading,0)},{speed}"
        #         ,9         ,10      ,11          ,12       ,13     ,14
        #      ###,cs        ,type    ,tail        ,from     ,to     ,timestamp
        part2 = f",{callsign},{actype},{tailnumber},{aptfrom},{aptto},{round(ts, 3)}"

        return (part1 + part2).replace("None", "")


    @staticmethod
    def getAbsoluteTime(f):
        """
        Method that returns the absolute emission time of a formatted message

        :param      f:    { parameter_description }
        :type       f:    { type_description }
        """
        a = f.split(",")
        if len(a) == 15:
            return a[-1]
        return None
