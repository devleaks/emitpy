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


class RTTFCFormatter(Formatter):

    FILE_FORMAT = "csv"

    def __init__(self, feature: "FeatureWithProps"):
        Formatter.__init__(self, feature=feature)
        self.name = "rttfc"

    def __str__(self):
        # RTTFC,hexid, lat, lon, baro_alt, baro_rate, gnd, track, gsp, cs_icao, ac_type, ac_tailno,
        #       from_iata, to_iata, timestamp, source, cs_iata, msg_type, alt_geom, IAS, TAS, Mach,
        #       track_rate, roll, mag_heading, true_heading, geom_rate, emergency, category,
        #       nav_qnh, nav_altitude_mcp, nav_altitude_fms, nav_heading, nav_modes, seen, rssi,
        #       winddir, windspd, OAT, TAT, isICAOhex,augmentation_status,authentication
        f = self.feature

        icao24x = f.getProp("icao24")
        hexid = int(icao24x, 16)

        coords = f.coords()
        lat= coords[1]
        lon= coords[0]

        baro_alt = f.altitude(0) / FT  # m -> ft
        baro_rate = f.prop("")

        airborne = (alt > 0 and speed > 20)
        gnd = not airborne  # :-)

        track = f.getProp("heading")
        gsp = f.speed(0) * 3.6 / NAUTICAL_MILE  # m/s in kn
        cs_icao= f.prop("")
        ac_type= f.getProp("aircraft:actype:actype")  # ICAO
        ac_tailno = f.getProp("aircraft:acreg")
        from_iata = f.getProp("departure:iata")
        to_iata = f.getProp("arrival:iata")

        timestamp = f.getProp(FEATPROP.EMIT_ABS_TIME.value)

        source = "emitpy"

        cs_iata = f.prop("")
        msg_type = f.prop("")
        alt_geom = f.prop("")
        ias = f.prop("")
        tas = f.prop("")
        mach = f.prop("")
        track_rate = f.prop("")
        roll = f.prop("")
        mag_heading = f.prop("")
        true_heading = f.prop("")
        geom_rate = f.prop("")
        emergency = f.prop("")
        category, = f.prop("")
        nav_qnh = f.prop("")
        nav_altitude_mcp = f.prop("")
        nav_altitude_fms = f.prop("")
        nav_heading = f.prop("")
        nav_modes = f.prop("")
        seen = f.prop("")
        rssi, = f.prop("")
        winddir = f.prop("")
        windspd = f.prop("")
        oat = f.prop("")
        tat = f.prop("")
        isicaohex = f.prop("")
        augmentation_status = f.prop("")
        authentication = f.prop("")

        coords = f.coords()

        alt = f.altitude(0) / FT  # m -> ft

        vspeed = f.vspeed(0) * FT * 60  # m/s -> ft/min
        speed = f.speed(0) * 3.6 / NAUTICAL_MILE  # m/s in kn

        heading = f.getProp("heading")

        actype = f.getProp("aircraft:actype:actype")  # ICAO
        if f.getProp("service-type") is not None:  # service
            callsign = f.getProp("vehicle:callsign").replace(" ","").replace("-","")
        else:  # fight
            callsign = f.getProp("aircraft:callsign").replace(" ","").replace("-","")
        tailnumber = f.getProp("aircraft:acreg")
        aptfrom = f.getProp("departure:icao")     # IATA
        aptto = f.getProp("arrival:icao")  # IATA
        ts = f.getProp(FEATPROP.EMIT_ABS_TIME.value)

        rttfc = f"RTTFC,{hexid},{lat},{lon},{baro_alt},{baro_rate},{gnd},{track},{gsp},{cs_icao},{ac_type},{ac_tailno},"
              + f"{from_iata},{to_iata},{timestamp},{source},{cs_iata},{msg_type},{alt_geom},{ias},{tas},{mach},"
              + f"{track_rate},{roll},{mag_heading},{true_heading},{geom_rate},{emergency},{category},"
              + f"{nav_qnh},{nav_altitude_mcp},{nav_altitude_fms},{nav_heading},{nav_modes},{seen},{rssi},"
              + f"{winddir},{windspd},{oat},{tat},{isicaohex},{augmentation_status},{authentication}"
        return rttfc.replace("None", "")
