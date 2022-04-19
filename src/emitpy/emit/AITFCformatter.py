#  Python classes to format features for output to different channel requirements
#
import logging
import datetime
import json

from ..constants import FEATPROP
from ..airport import Airport
from ..utils import FT, NAUTICAL_MILE

from .format import Formatter

logger = logging.getLogger("LiveTrafficFormatter")


class AITFCFormatter(Formatter):

    FILE_FORMAT = "csv"

    def __init__(self, feature: "FeatureWithProps"):
        Formatter.__init__(self, feature=feature)
        self.name = "lt"

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
        f = self.feature

        icao24x = f.getProp("icao24")
        icao24 = int(icao24x, 16)

        coords = f.coords()

        alt = f.altitude(0) / FT  # m -> ft

        vspeed = f.vspeed(0) * FT * 60  # m/s -> ft/min
        speed = f.speed(0) * 3.6 / NAUTICAL_MILE  # m/s in kn
        airborne = (alt > 0 and speed > 20)

        heading = f.getProp("heading")

        actype = f.getProp("aircraft:actype:actype")  # ICAO
        if f.getProp("service-type") is not None or f.getProp("mission") is not None:  # mission or service
            callsign = f.getProp("vehicle:callsign").replace(" ","").replace("-","")
            tailnumber = f.getProp("vehicle:icao")
        else:  # fight
            callsign = f.getProp("aircraft:callsign").replace(" ","").replace("-","")
            tailnumber = f.getProp("aircraft:acreg")
        aptfrom = f.getProp("departure:icao")     # IATA
        aptto = f.getProp("arrival:icao")  # IATA
        ts = f.getProp(FEATPROP.EMIT_ABS_TIME.value)
        #         0    ,1       ,2          ,3          ,4    ,5       ,6                     ,7                 ,8
        #         AITFC,hexid   ,lat        ,lon        ,alt  ,vs      ,airborne              ,hdg               ,spd ### ,cs,type,tail,from,to,timestamp
        part1 = f"AITFC,{icao24},{coords[1]},{coords[0]},{alt},{vspeed},{1 if airborne else 0},{round(heading,0)},{speed}"
        #         ,9         ,10      ,11          ,12       ,13     ,14
        #      ###,cs        ,type    ,tail        ,from     ,to     ,timestamp
        part2 = f",{callsign},{actype},{tailnumber},{aptfrom},{aptto},{round(ts, 3)}"

        return (part1 + part2).replace("None", "")


class LiveTrafficWeather(Formatter):

    FILE_FORMAT = "csv"

    def __init__(self, metar):
        Formatter.__init__(self, feature=None)
        self.fileformat = "json"
        self.metar = metar

    def __str__(self):
        weather = {
            "ICAO": self.metar.station_id,
            "QNH": self.metar.pressure("MB"),
            "METAR": self.metar.metarcode,
            "NAME": Airport.findICAO(self.metar.station_id)
        }
        logger.debug(f"LiveTrafficWeather: {weather}")
        return json.dumps(weather)
