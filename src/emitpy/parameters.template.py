"""
Application parameters not related to the simulation.
Used for file location, connection details, etc.
"""
import os


DEVELOPMENT = True  # produces additional debug if True
PRODUCTION  = True  # removes caches and short circuits


# ######################
# File system-based Data
#
# Should not be specified, should be deduced from Emitpy.__FILE__
HOME_DIR = os.path.join("<application-home-directory>")  # should work even on windows... python guys are genius.

# DATA is a database of *static* data, definitions, etc. (read-only)
DATA_DIR = os.path.join(HOME_DIR, "data")

# AODB is a database of working data (read-write). Mostly replaced by Redis.
TEMP_DIR = os.path.join(HOME_DIR, "db")

# Cache dir is for pickle dumps.
CACHE_DIR = os.path.join(TEMP_DIR, "cache")

# METAR storage directory
METAR_DIR = os.path.join(TEMP_DIR, "metar")


# ######################
# Database system-based Data
#
REDIS_CONNECT = {
    "host": "<redis-host>",
    "port": 6379,
    "db": 0
}

# See https://github.com/mrtolkien/fastapi_simple_security
SECURE_API   = True  # Whether to use api-key for all requests
ALLOW_KEYGEN = True  # Whether to mount api to generate keys, should be false in production

# ######################
# Application options and parameters
#
# Managed Airport we are working on
MANAGED_AIRPORT = {
    "ICAO": "OTHH",
    "IATA": "DOH",
    "name": "Hamad International Airport",
    "name_local": "مطار حمد الدولي",
    "city": "Doha",
    "country": "Qatar",
    "regionName": "Qatar",
    "elevation": 13.0,
    "lat": 25.2745,
    "lon": 51.6077,
    "tzoffset": 3,
    "tzname": "Doha",
    "operator": "MATAR"
}

MANAGED_AIRPORT_DIR  = os.path.join(DATA_DIR, "managedairport", MANAGED_AIRPORT["ICAO"])
MANAGED_AIRPORT_AODB = os.path.join(TEMP_DIR, MANAGED_AIRPORT["ICAO"])
MANAGED_AIRPORT_CACHE = os.path.join(CACHE_DIR, MANAGED_AIRPORT["ICAO"])  # os.path.join(MANAGED_AIRPORT_AODB, "cache")

# Broadcaster
BROADCASTER_HEARTBEAT = False

# Sources of some data
METAR_URL = "http://tgftp.nws.noaa.gov/data/observations/metar/stations"
METAR_HISTORICAL = False

# X-Plane location
XPLANE_DIR = os.path.join("<x-plane-home-directory>")
XPLANE_FEED = False
XPLANE_HOSTNAME = "<x-plane-host-ip-address>"
XPLANE_PORT = 49003
