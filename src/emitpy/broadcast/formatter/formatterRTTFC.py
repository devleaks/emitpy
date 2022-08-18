#  Python classes to format features for output to different channel requirements
#
import logging
import datetime
import json

from emitpy.constants import FEATPROP
from emitpy.airport import Airport
from emitpy.utils import FT, NAUTICAL_MILE

from .formatter import Formatter

logger = logging.getLogger("RTTFCFormatter")


class RTTFCFormatter(Formatter):

    NAME = "rttfc"

    def __init__(self, feature: "FeatureWithProps"):
        Formatter.__init__(self, name=RTTFCFormatter.NAME, feature=feature)
        self.name = "rttfc"

    def __str__(self):
        f = self.feature

        rttfcObj = {
          "RTTFC": "RTTFC",
          "hexid": "efface",
          "lat": f.lat(),
          "lon": f.lon(),
          "baro_alt": f.altitude(0) / FT,
          "baro_rate": 0,
          "gnd": 1,  # default will be updated below
          "track": f.getProp(FEATPROP.HEADING.value),
          "gsp": f.speed(0) * 3.6 / NAUTICAL_MILE,
          "cs_icao": "CSICAO",
          "ac_type": "ZZZC",
          "ac_tailno": "TAILNUM",
          "from_iata": "",
          "to_iata": "",
          "timestamp": f.getProp(FEATPROP.EMIT_ABS_TIME.value),
          "source": "X2",
          "cs_iata": "CSIATA",
          "msg_type": "adsb_icao",
          "alt_geom": -1,
          "IAS": -1,
          "TAS": -1,
          "Mach": -1,
          "track_rate": -1,
          "roll": -1,
          "mag_heading": -1,
          "true_heading": f.getProp(FEATPROP.HEADING.value),
          "geom_rate": -1,
          "emergency": "",
          "category": "A3",
          "nav_qnh": -1,
          "nav_altitude_mcp": -1,
          "nav_altitude_fms": -1,
          "nav_heading": -1,
          "nav_modes": "",
          "seen": 60,
          "rssi": -1,
          "winddir": -1,
          "windspd": -1,
          "OAT": -1,
          "TAT": -1,
          "isICAOhex": 0,
          "augmentation_status": 262609,
          "authentication": ""
        }
        # rttfcObj = {
        #     "RTTFC": "RTTFC",
        #     "hexid": int(f.getPropPath("flight.aircraft.icao24"), 16),
        #     "lat": f.lat(),
        #     "lon": f.lon(),
        #     "baro_alt": f.altitude(0) / FT,  # m -> ft
        #     "baro_rate": "",
        #     "gnd": "",
        #     "track": f.getProp(FEATPROP.HEADING.value),
        #     "gsp": f.speed(0) * 3.6 / NAUTICAL_MILE,  # m/s in kn"
        #     "cs_icao": "",
        #     "ac_type": "",
        #     "ac_tailno": "",
        #     "from_iata": "",
        #     "to_iata": "",
        #     "timestamp": f.getProp(FEATPROP.EMIT_ABS_TIME.value),
        #     "source": "EP",
        #     "cs_iata": "",
        #     "msg_type": "other",
        #     "alt_geom": -1,
        #     "ias": -1,
        #     "tas": -1,
        #     "mach": -1.0,
        #     "track_rate": -1.0,
        #     "roll": -1.0,
        #     "mag_heading": -1.0,
        #     "true_heading": f.getProp(FEATPROP.HEADING.value),
        #     "geom_rate": -1,
        #     "emergency": "",
        #     "category": "",
        #     "nav_qnh": -1,
        #     "nav_altitude_mcp": -1,
        #     "nav_altitude_fms": -1,
        #     "nav_heading": -1.00,
        #     "nav_modes": "",
        #     "seen": "",
        #     "rssi": "",
        #     "winddir": -1,
        #     "windspd": -1,
        #     "oat": -1,
        #     "tat": -1,
        #     "isicaohex": 0,  # we randomly generate it...
        #     "augmentation_status": "",
        #     "authentication": ""
        # }

        airborne = (rttfcObj["baro_alt"] > 0 and rttfcObj["gsp"] > 50)  # should be: speed < min(takeoff_speed, landing_speed)
        rttfcObj["gnd"] = 0 if not airborne else 1  # :-)

        emit_type = f.getPropPath("$.emit.emit-type")
        if emit_type == "flight":
            rttfcObj["ac_type"] = f.getPropPath("$.flight.aircraft.actype.base-type.actype")  # ICAO A35K
            rttfcObj["hexid"] = int(f.getPropPath("flight.aircraft.icao24"), 16)

            callsign = f.getPropPath("$.flight.callsign")
            if callsign is not None:
                rttfcObj["cs_icao"] = callsign.replace(" ","").replace("-","")
            callsign = f.getPropPath("$.flight.flightnumber")
            if callsign is not None:
                rttfcObj["cs_iata"] = callsign.replace(" ","").replace("-","")
            rttfcObj["ac_tailno"] = f.getPropPath("$.flight.aircraft.acreg")
            rttfcObj["from_iata"] = f.getPropPath("$.flight.departure.airport.iata")
            rttfcObj["to_iata"] = f.getPropPath("$.flight.arrival.airport.iata")

        elif emit_type == "service":
            rttfcObj["hexid"] = int(f.getPropPath("service.vehicle.icao24"), 16)
            # rttfcObj["ac_type"] = f.getPropPath("$.service.vehicle.icao")  # ICAO A35K

            callsign = f.getPropPath("$.service.vehicle.callsign")
            if callsign is not None:
                rttfcObj["cs_iata"] = callsign.replace(" ","").replace("-","")
                rttfcObj["cs_icao"] = callsign.replace(" ","").replace("-","")
            rttfcObj["ac_tailno"] = f.getPropPath("$.service.vehicle.registration")
            # ac_type blank for ground vehicle

        elif emit_type == "mission":
            rttfcObj["hexid"] = int(f.getPropPath("mission.vehicle.icao24"), 16)
            # rttfcObj["ac_type"] = f.getPropPath("$.service.vehicle.icao")  # ICAO A35K

            callsign = f.getPropPath("$.mission.vehicle.callsign")
            if callsign is not None:
                rttfcObj["cs_iata"] = callsign.replace(" ","").replace("-","")
                rttfcObj["cs_icao"] = callsign.replace(" ","").replace("-","")
            rttfcObj["ac_tailno"] = f.getPropPath("$.mission.vehicle.registration")
            # ac_type blank for ground vehicle

        else:
            logger.warning(f":__str__: invalid emission type {emit_type}")
            return None

        return ",".join([str(f) for f in rttfcObj.values()]).replace("None", "")


    @staticmethod
    def getAbsoluteTime(f):
        """
        Method that returns the absolute emission time of a formatted message

        :param      f:    { parameter_description }
        :type       f:    { type_description }
        """
        a = f.split(",")
        if len(a) == 43:  # len()>15?
            return a[14]
        return None

# ###########################################
#
# • RTTFC
# • hexid
# • lat = latitude
# • lon = longitude
# • baro_alt = barometric altitude
# • baro_rate = barometric vertical rate
# • gnd = ground flag
# • track = track
# • gsp = ground speed
# • cs_icao = ICAO call sign
# • ac_type = aircraft type
# • ac_tailno = aircraft registration
# • from_iata = origin IATA code
# • to_iata = destination IATA code
# • timestamp = unix epoch timestamp when data was last updated
# • source = data source
# • cs_iata = IATA call sign
# • msg_type = type of message
# • alt_geom = geometric altitude (WGS84 GPS altitude)
# • IAS = indicated air speed
# • TAS = true air speed
# • Mach = Mach number
# • track_rate = rate of change for track
# • roll = roll in degrees, negative = left
# • mag_heading = magnetic heading
# • true_heading = true heading
# • geom_rate = geometric vertical rate
# • emergency = emergency status
# • category = category of the aircraft
# • nav_qnh = QNH setting navigation is based on
# • nav_altitude_mcp = altitude dialled into the MCP in the flight deck
# • nav_altitude_fms = altitude set by the flight management system (FMS)
# • nav_heading = heading set by the MCP
# • nav_modes = which modes the autopilot is currently in
# • seen = seconds since any message updated this aircraft state vector
# • rssi = signal strength of the receiver
# • winddir = wind direction in degrees true north
# • windspd = wind speed in kts
# • OAT = outside air temperature / static air temperature
# • TAT = total air temperature
# • isICAOhex = is this hexid an ICAO assigned ID.
# • Augmentation_status = has this record been augmented from multiple sources
# • Authentication = authentication status of the license, safe to ignore.
#
# ###########################################
#
# RTTFC,hexid, lat, lon, baro_alt, baro_rate, gnd, track, gsp, cs_icao, ac_type, ac_tailno,
#       from_iata, to_iata, timestamp, source, cs_iata, msg_type, alt_geom, IAS, TAS, Mach,
#       track_rate, roll, mag_heading, true_heading, geom_rate, emergency, category,
#       nav_qnh, nav_altitude_mcp, nav_altitude_fms, nav_heading, nav_modes, seen, rssi,
#       winddir, windspd, OAT, TAT, isICAOhex,augmentation_status,authentication

# RTTFC,hexid,  lat,      lon,      baro_alt, baro_rate, gnd, track, gsp, cs_icao, ac_type, ac_tailno,from_iata, to_iata, timestamp,              source, cs_iata,  msg_type, alt_geom, IAS, TAS, Mach,track_rate, roll, mag_heading, true_heading, geom_rate, emergency, category,nav_qnh, nav_altitude_mcp, nav_altitude_fms, nav_heading, nav_modes, seen, rssi, winddir, windspd, OAT, TAT, isICAOhex, augmentation_status, authentication
# RTTFC,9004093,25.175100,51.675200,3450    ,13        , 0  ,115   , 139,  ETD394,    A321,    A6-AEG,         ,        ,       256, OpenSky Live Online,  ETD394, lt_export,     3092,  -1,  -1,   -1,        -1,   -1,          -1,       114.67,        13,      none,         ,     -1,               -1,               -1,          -1,        -1,   -1,   -1,      -1,      -1,  -1,  -1,         1,                    ,

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
# RTTFC,9004338,25.185500,55.485600,2150,-4,0,301,97,FDB866,B38M,A6-FMM,,,102,OpenSky Live Online,FDB866,lt_export,1792,-1,-1,-1,-1,-1,-1,301.49,-4,none,,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,1,,
# RTTFC,4958674,25.259500,55.359800,325,3,0,301,86,THY2YH,A333,TC-JNR,,,103,OpenSky Live Online,THY2YH,lt_export,-33,-1,-1,-1,-1,-1,-1,301.32,3,none,,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,1,,
# RTTFC,9004023,25.252300,55.378200,0,0,1,121,5,A6EOZ,A388,A6-EOZ,,,103,OpenSky Live Online,A6EOZ,lt_export,0,-1,-1,-1,-1,-1,-1,120.94,0,none,,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,1,,
# RTTFC,7389446,25.254600,55.364900,0,0,1,121,9,OMA604,B38M,A4O-MK,,,103,OpenSky Live Online,OMA604,lt_export,0,-1,-1,-1,-1,-1,-1,120.94,0,none,,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,1,,
# RTTFC,9003829,25.426700,55.310500,5700,11,0,23,141,FDB5DA,B738,A6-FED,,,109,OpenSky Live Online,FDB5DA,lt_export,5342,-1,-1,-1,-1,-1,-1,23.20,11,none,,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,1,,
# RTTFC,9006849,25.253300,55.351300,0,0,1,31,1,SW10,ZZZC,,,,124,OpenSky Live Online,SW10,lt_export,0,-1,-1,-1,-1,-1,-1,30.94,0,none,C2,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,1,,
# RTTFC,9006794,25.264100,55.347900,0,0,1,174,3,CM4,ZZZC,,,,126,OpenSky Live Online,CM4,lt_export,0,-1,-1,-1,-1,-1,-1,174.38,0,none,C2,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,1,,
# RTTFC,8392033,25.256000,55.349000,0,0,1,31,1,IGO064,A20N,VT-IZU,,,129,OpenSky Live Online,IGO064,lt_export,0,-1,-1,-1,-1,-1,-1,30.94,0,none,,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,1,,
# RTTFC,9006778,25.250900,55.363700,0,0,1,253,4,,,,,,135,OpenSky Live Online,,lt_export,0,-1,-1,-1,-1,-1,-1,253.12,0,none,,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,1,,
# RTTFC,9006778,25.250900,55.363700,0,0,1,253,4,,ZZZC,,,,135,OpenSky Live Online,,lt_export,0,-1,-1,-1,-1,-1,-1,253.12,0,none,C2,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,1,,
# RTTFC,3949968,25.262900,55.360000,0,0,1,42,1,BOX513,,,,,137,OpenSky Live Online,BOX513,lt_export,0,-1,-1,-1,-1,-1,-1,42.19,0,none,,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,1,,
#