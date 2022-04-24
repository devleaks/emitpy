"""
RTTFC,hexid, lat, lon, baro_alt, baro_rate, gnd, track, gsp, cs_icao, ac_type, ac_tailno, from_iata, to_iata, timestamp, source, cs_iata, msg_type, alt_geom, IAS, TAS, Mach, track_rate, roll, mag_heading, true_heading, geom_rate, emergency, category, nav_qnh, nav_altitude_mcp, nav_altitude_fms, nav_heading, nav_modes, seen, rssi, winddir, windspd, OAT, TAT, isICAOhex,augmentation_status,authentication

Examples:
RTTFC,11234042,-33.9107,152.9902,26400,1248,0,90.12,490.00,AAL72,B789, N835AN,SYD,LAX,1645144774.2,X2,AA72,adsb_icao,27575,320,474,0.780, 0.0,0.0,78.93,92.27,1280,none,A5,1012.8,35008,-1,71.02, autopilot|vnav|lnav|tcas,0.0,-21.9,223,24,-30,0,1,170124
RTTFC,10750303,-33.7964,152.3938,20375,1376,0,66.77,484.30,UAL842,B789, N35953,SYD,LAX,1645144889.8,X2,UA842,adsb_icao,21350,343,466,0.744,-0.0, 0.5,54.49,67.59,1280,none,A5,1012.8,35008,-1,54.84, autopilot|vnav|lnav|tcas,0.0,-20.8,227,19,-15,14,1,268697

"""


hexid = ""  # hexid
lat = ""  # latitude
lon = ""  # longitude
baro_alt = ""  # barometric altitude
baro_rate = ""  # barometric vertical rate
gnd = ""  # ground flag
track = ""  # track
gsp = ""  # ground speed
cs_icao = ""  # ICAO call sign
ac_type = ""  # aircraft type
ac_tailno = ""  # aircraft registration
from_iata = ""  # origin IATA code
to_iata = ""  # destination IATA code
timestamp = ""  # unix epoch timestamp when data was last updated
source = ""     # data source: The “source” field can contain the following values:
                # adsb_icao: messages from a Mode S or ADS-B transponder.
                # adsb_icao_nt: messages from an ADS-B equipped "non-transponder" emitter e.g. a ground vehicle.
                # adsr_icao: rebroadcast of an ADS-B messages originally sent via another data link
                # tisb_icao: traffic information about a non-ADS-B target identified by a 24-bit ICAO address, e.g. a Mode S target tracked by SSR.
                # adsc: ADS-C (received by satellite downlink) – usually old positions, check tstamp.
                # mlat: MLAT, position calculated by multilateration. Usually somewhat inaccurate.
                # other: quality/source unknown. Use caution.
                # mode_s: ModeS data only, no position.
                # adsb_other: using an anonymised ICAO address. Rare.
                # adsr_other: rebroadcast of ‘adsb_other’ ADS-B messages.
                # tisb_other: traffic information about a non-ADS-B target using a non-ICAO address
                # tisb_trackfile: traffic information about a non-ADS-B target using a track/file identifier, typically from primary or Mode A/C radar
cs_iata = ""  # IATA call sign
msg_type = ""  # type of message
alt_geom = ""  # geometric altitude (WGS84 GPS altitude)
IAS = ""  # indicated air speed
TAS = ""  # true air speed
Mach = ""  # Mach number
track_rate = ""  # rate of change for track
roll = ""  # roll in degrees, negative = ""  # left
mag_heading = ""  # magnetic heading
true_heading = ""  # true heading
geom_rate = ""  # geometric vertical rate
emergency = ""  # emergency status
category = ""  # category of the aircraft
nav_qnh = ""  # QNH setting navigation is based on
nav_altitude_mcp = ""  # altitude dialled into the MCP in the flight deck
nav_altitude_fms = ""  # altitude set by the flight management system (FMS)
nav_heading = ""  # heading set by the MCP
nav_modes = ""  # which modes the autopilot is currently in
seen = ""  # seconds since any message updated this aircraft state vector
rssi = ""  # signal strength of the receiver
winddir = ""  # wind direction in degrees true north
windspd = ""  # wind speed in kts
OAT = ""  # outside air temperature / static air temperature
TAT = ""  # total air temperature
isICAOhex = ""  # is this hexid an ICAO assigned ID.
Augmentation_status = ""  # has this record been augmented from multiple sources
Authentication = ""  # authentication status of the license, safe to ignore


