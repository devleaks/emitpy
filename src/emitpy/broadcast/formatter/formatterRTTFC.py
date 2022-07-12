#  Python classes to format features for output to different channel requirements
#
import logging
import datetime
import json

from emitpy.constants import FEATPROP
from emitpy.airport import Airport
from emitpy.utils import FT, NAUTICAL_MILE

from .formatter import FormatterBase

logger = logging.getLogger("RTTFCFormatter")


class RTTFCFormatter(FormatterBase):

    NAME = "rttfc"

    def __init__(self, feature: "FeatureWithProps"):
        FormatterBase.__init__(self, name=RTTFCFormatter.NAME, feature=feature)
        self.name = "rttfc"

    def __str__(self):
        # RTTFC,hexid, lat, lon, baro_alt, baro_rate, gnd, track, gsp, cs_icao, ac_type, ac_tailno,
        #       from_iata, to_iata, timestamp, source, cs_iata, msg_type, alt_geom, IAS, TAS, Mach,
        #       track_rate, roll, mag_heading, true_heading, geom_rate, emergency, category,
        #       nav_qnh, nav_altitude_mcp, nav_altitude_fms, nav_heading, nav_modes, seen, rssi,
        #       winddir, windspd, OAT, TAT, isICAOhex,augmentation_status,authentication
        #
        # RTTFC,7389381,25.290900,51.590000,0,0,1,245,4,QTR1399,A333,A4O-DI,OTHH,DTTA,249,OpenSky Live Online,QTR1399,lt_export,0,-1,-1,-1,-1,-1,-1,244.69,0,none,,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,1,,
        # RTTFC,7389381,25.290900,51.590000,0,0,1,245,4,QTR1399,A333,A4O-DI,OTHH,DTTA,249,OpenSky Live Online,QTR1399,lt_export,0,-1,-1,-1,-1,-1,-1,244.69,0,none,,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,1,,
        # RTTFC,434334,25.282000,51.593700,0,0,1,158,34,QTR209,A320,A7-AHW,,,250,OpenSky Live Online,QTR209,lt_export,0,-1,-1,-1,-1,-1,-1,157.50,0,none,,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,1,,
        # RTTFC,9004093,25.175100,51.675200,3450,13,0,115,139,ETD394,A321,A6-AEG,,,256,OpenSky Live Online,ETD394,lt_export,3092,-1,-1,-1,-1,-1,-1,114.67,13,none,,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,1,,
        # RTTFC,9004049,25.283200,51.614600,375,0,0,159,52,ABY136,A320,A6-AOE,,,256,OpenSky Live Online,ABY136,lt_export,17,-1,-1,-1,-1,-1,-1,158.51,0,none,,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,1,,
        # RTTFC,434505,25.288900,51.606700,0,0,1,338,0,QTR76R,A388,A7-APH,,,302,OpenSky Live Online,QTR76R,lt_export,0,-1,-1,-1,-1,-1,-1,337.50,0,none,,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,1,,
        # RTTFC,4949106,25.281200,51.610000,0,0,1,248,1,QTR8409,B744,TC-ACR,VHHH,OTHH,308,OpenSky Live Online,QTR8409,lt_export,0,-1,-1,-1,-1,-1,-1,247.50,0,none,,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,1,,
        # RTTFC,9004093,25.160500,51.749900,5975,12,0,101,141,ETD394,A321,A6-AEG,,,311,OpenSky Live Online,ETD394,lt_export,5617,-1,-1,-1,-1,-1,-1,101.39,12,none,,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,1,,
        # RTTFC,9004049,25.245300,51.630900,1525,4,0,157,91,ABY136,A320,A6-AOE,,,311,OpenSky Live Online,ABY136,lt_export,1167,-1,-1,-1,-1,-1,-1,157.36,4,none,,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,1,,
        #
        def getprop(path: str):
            r = JSONPath(path).parse(self.feature.properties)
            if len(r) == 1:
                return r[0]
            elif len(r) > 1:
                logger.warning(f":__str__: ambiguous return value for {path}")
                return r[0]
            return None


        icao24x = getProp("flight.aircraft.icao24")
        hexid = int(icao24x, 16)

        icao24x = f.getProp(FEATPROP.ICAO24.value)
        if icao24x is not None:
            icao24 = int(str(icao24x), 16)  # https://stackoverflow.com/questions/46341329/int-cant-convert-non-string-with-explicit-base-when-converting-to-gui
        else:
            icao24 = None

        coords   = f.coords()

        baro_alt = f.altitude(0) / FT  # m -> ft
        baro_rate = 0

        vspeed   = f.vspeed(0) * FT * 60  # m/s -> ft/min
        speed    = f.speed(0) * 3.6 / NAUTICAL_MILE  # m/s in kn

        airborne = (alt > 0 and speed > 50)
        gnd = not airborne  # :-)

        track  = f.getProp(FEATPROP.HEADING.value)

        gsp = f.speed(0) * 3.6 / NAUTICAL_MILE  # m/s in kn



        timestamp = f.getProp(FEATPROP.EMIT_ABS_TIME.value)
        source = "emitpy"

        emit_type = getprop("$.emit.emit-type")

        if emit_type == "flight":
            actype = getprop("$.flight.aircraft.actype.base-type.actype")  # ICAO A35K
            callsign = getprop("$.flight.callsign").replace(" ","").replace("-","")
            ac_tailno = getprop("$.flight.aircraft.acreg")

            from_iata = getprop("$.flight.departure.iata")
            to_iata = getprop("$.flight.arrival.iata")

            aptfrom = getprop("$.flight.departure.icao")     # IATA
            aptto = getprop("$.flight.arrival.icao")  # IATA

            cs_icao= getProp("$.flight.aircraft.callsign")
            cs_iata = getProp("$.flight.flightnumber").replace(" ", "")

            alt_geom = f.getProp("")
            ias = f.getProp("")
            tas = f.getProp("")
            mach = f.getProp("")
            track_rate = f.getProp("")
            roll = f.getProp("")

        elif emit_type == "service":
            callsign = getprop("$.service.vehicle.callsign").replace(" ","").replace("-","")
            ac_tailno = getprop("$.service.vehicle.registration")
            actype = getprop("$.service.vehicle.icao")
            from_iata = ""
            to_iata = ""
            aptfrom = ""
            aptto = ""

        elif emit_type == "mission":
            callsign = getprop("$.mission.vehicle.callsign").replace(" ","").replace("-","")
            ac_tailno = getprop("$.mission.vehicle.registration")
            actype = getprop("$.mission.vehicle.icao")
            from_iata = ""
            to_iata = ""
            aptfrom = ""
            aptto = ""

        else:
            logger.warning(f":__str__: invalid emission type {emit_type}")
            return None


        msg_type = f.getProp("")
        mag_heading = f.getProp("")
        true_heading = f.getProp("")

        geom_rate = f.getProp("")
        emergency = f.getProp("")
        category, = f.getProp("")

        nav_qnh = f.getProp("")
        nav_altitude_mcp = f.getProp("")
        nav_altitude_fms = f.getProp("")
        nav_heading = f.getProp("")
        nav_modes = f.getProp("")

        seen = f.getProp("")
        rssi, = f.getProp("")

        winddir = f.getProp("")
        windspd = f.getProp("")
        oat = f.getProp("")
        tat = f.getProp("")

        isicaohex = f.getProp("")

        augmentation_status = f.getProp("")
        authentication = f.getProp("")


        rttfc = f"RTTFC,{hexid},{lat},{lon},{baro_alt},{baro_rate},{gnd},{track},{gsp},{cs_icao},{ac_type},{ac_tailno},"
              + f"{from_iata},{to_iata},{timestamp},{source},{cs_iata},{msg_type},{alt_geom},{ias},{tas},{mach},"
              + f"{track_rate},{roll},{mag_heading},{true_heading},{geom_rate},{emergency},{category},"
              + f"{nav_qnh},{nav_altitude_mcp},{nav_altitude_fms},{nav_heading},{nav_modes},{seen},{rssi},"
              + f"{winddir},{windspd},{oat},{tat},{isicaohex},{augmentation_status},{authentication}"
        return rttfc.replace("None", "")
