#  Python classes to format features for output to different channel requirements
#
import logging
import datetime
import json
import flatdict

from emitpy.constants import FEATPROP
from emitpy.utils import convert

from .formatter import Formatter

logger = logging.getLogger("AITFCFormatter")


class AITFCFormatter(Formatter):
    NAME = "aitfc"
    FILE_EXTENSION = "csv"

    def __init__(self, feature: "FeatureWithProps"):
        Formatter.__init__(self, name=AITFCFormatter.NAME, feature=feature)

    def __str__(self):
        f = self.feature
        # fp = dict(flatdict(f.properties))  # we only flatten props

        icao24x = f.getProp(FEATPROP.ICAO24.value)
        if icao24x is not None:
            icao24 = int(str(icao24x), 16)  # https://stackoverflow.com/questions/46341329/int-cant-convert-non-string-with-explicit-base-when-converting-to-gui
        else:
            icao24 = None

        coords = f.coords()

        alt = convert.meters_to_feet(f.altitude(0))  # m -> ft

        vspeed = convert.feet_to_meters(f.vspeed(0)) * 60  # m/s -> ft/min
        speed = convert.ms_to_kn(f.speed(0))  # m/s in kn
        airborne = alt > 0 and speed > 20

        course = f.course()

        emit_type = f.getPropPath("$.emit.emit-type")

        if emit_type == "flight":
            actype = f.getPropPath("$.flight.aircraft.actype.base-type.actype")  # ICAO A35K
            callsign = f.getPropPath("$.flight.callsign").replace(" ", "").replace("-", "")
            tailnumber = f.getPropPath("$.flight.aircraft.acreg")
            aptfrom = f.getPropPath("$.flight.departure.icao")  # IATA
            aptto = f.getPropPath("$.flight.arrival.icao")  # IATA
        elif emit_type == "service":
            callsign = f.getPropPath("$.service.vehicle.callsign").replace(" ", "").replace("-", "")
            tailnumber = f.getPropPath("$.service.vehicle.registration")
            actype = f.getPropPath("$.service.vehicle.icao")
            aptfrom = ""
            aptto = ""
        elif emit_type == "mission":
            callsign = f.getPropPath("$.mission.vehicle.callsign").replace(" ", "").replace("-", "")
            tailnumber = f.getPropPath("$.mission.vehicle.registration")
            actype = f.getPropPath("$.mission.vehicle.icao")
            aptfrom = ""
            aptto = ""
        else:
            logger.warning(f"invalid emission type {emit_type}")
            return None

        ts = f.getProp(FEATPROP.EMIT_ABS_TIME)
        #         0    ,1       ,2          ,3          ,4    ,5       ,6                     ,7                 ,8
        #         AITFC,hexid   ,lat        ,lon        ,alt  ,vs      ,airborne              ,hdg               ,spd ### ,cs,type,tail,from,to,timestamp
        part1 = f"AITFC,{icao24},{coords[1]},{coords[0]},{alt},{vspeed},{1 if airborne else 0},{round(course,0)},{speed}"
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


# ###########################################
#
# • AITFC
# • Hexid: the hexadecimal ID of the transponder of the aircraft. This is a unique ID, and you can use this ID to track individual aircraft.
# • Lat: latitude in degrees
# • Lon: longitude in degrees
# • Alt: altitude in feet
# • Vs: vertical speed in ft/min
# • Airborne: 1 or 0
# • Hdg: The course of the aircraft (it’s actually the true track, strictly speaking. )
# • Spd: The speed of the aircraft in knots
# • Cs: the ICAO callsign (Emirates 413 = UAE413 in ICAO speak, = EK413 in IATA speak)
# • Type: the ICAO type of the aircraft, e.g. A388 for Airbus 380-800. B789 for Boeing 787-9 etc.
# • Tail: The registration number of the aircraft
# • From: The origin airport where known (in IATA or ICAO code)
# • To: The destination airport where known (in IATA or ICAO code)
# • Timestamp: The UNIX epoch timestamp when this position was valid
#
# ###########################################
#
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
