"""
AITFC,hexid,lat,lon,alt,vs,airborne,hdg,spd,cs,type,tail,from,to,timestamp


"""

# Foreflight XTRAFFICPSX
hexid = ""  #  the hexadecimal ID of the transponder of the aircraft. This is a unique ID, and you can use this ID to track individual aircraft.
lat = ""  #  latitude in degrees
lon = ""  #  longitude in degrees
alt = ""  #  altitude in feet
vs = ""  #  vertical speed in ft/min
airborne = ""  #  1 or 0
hdg = ""  #  The heading of the aircraft (it’s actually the true track, strictly speaking. )
spd = ""  #  The speed of the aircraft in knots
cs = ""  #  the ICAO callsign (Emirates 413 = UAE413 in ICAO speak, = EK413 in IATA speak)
xtype = ""  #  the ICAO type of the aircraft, e.g. A388 for Airbus 380-800. B789 for Boeing 787-9 etc.
# additional fields for AITFC
tail = ""  #  The registration number of the aircraft
xfrom = ""  #  The origin airport where known (in IATA or ICAO code)
to = ""  #  The destination airport where known (in IATA or ICAO code)
timestamp = ""  #  The UNIX epoch timestamp when this position was valid