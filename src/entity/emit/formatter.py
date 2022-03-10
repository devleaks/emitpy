#  Python classes to format features for output to different channel requirements
#
import logging
import datetime
import json

logger = logging.getLogger("Formatter")


class Formatter:

    def __init__(self, feature: "Feature"):
        self.feature = feature

    def __str__(self):
        return json.dumps(self.feature)



class LiveTraffic(Formatter):

    def __init__(self, feature: "Feature"):
        Formatter.__init__(self, feature=feature)
        self.metar = None

    def __str__(self):
        # Sample SendTraffic.py file:
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
        f = self.feature
        icao24x = f.getProp("icao24")
        print(">>>", icao24x)
        icao24 = int(icao24x, 16)
        coords = f["geometry"]["coordinates"]
        vspeed = f.getProp("vspeed")
        speed = f.getProp("speed")
        airborne = ((vspeed != 0) and (speed > 20))  # @todo
        heading = f.getProp("heading")

        actype = f.getProp("actype")  # ICAO
        callsign = f.getProp("callsign")
        tailnumber = f.getProp("acreg")
        aptfrom = f.getProp("origin")     # IATA
        aptto = f.getProp("destination")  # IATA
        ts = f.getProp("emission_ts")

        #        AITFC ,hexid   ,lat        ,lon        ,alt        ,vs      ,airborne              ,hdg               ,spd ### ,cs,type,tail,from,to,timestamp
        part1 = f"AITFC,{icao24},{coords[1]},{coords[0]},{coords[2]},{vspeed},{1 if airborne else 0},{round(heading,0)},{speed}"
        #      ###,cs        ,type    ,tail   ,from     ,to     ,timestamp
        part2 = f",{callsign},{actype},{acreg},{aptfrom},{aptto},{ts}"

        return part1 + part2


class LiveTrafficWeather:

    def __init__(self, metar):
        self.metar = metar

    def __str__(self):
        weather = {
            "ICAO": "EDKB",
            "QNH": "1013",
            "METAR": "EDKB Q1013",
            "NAME": "Bonn/Hangelar airport"
        }
        return json.dumps(weather)
