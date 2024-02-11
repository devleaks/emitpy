"""
Application parameters not related to the simulation.
Used for file location, connection details, etc.
"""

import os


DEVELOPMENT = True  # produces additional debug if True
PRODUCTION = True  # removes caches and short circuits


# ######################
# Managed Airport we are working on
#
MANAGED_AIRPORT_ICAO = None  # there is no default value

MANAGED_AIRPORT_OPERATOR = "MATAR"  # default is "AIRPORT_OPERATOR"
MANAGED_AIRPORT_HANDLER = "QAS"  # default is "AIRPORT_HANDLER"
MANAGED_AIRPORT_MISSION_HANDLER = "HIA"  # default is "MISSION_HANDLER"


# ######################
# File system-based Data
#
# Should not be specified, should be deduced from Emitpy.__FILE__
HOME_DIR = os.path.join(
    "<application-home-directory>"
)  # should work even on windows... python guys are genius.

# DATA is a database of *static* data, definitions, etc. (read-only)
DATA_DIR = os.path.join(HOME_DIR, "data")

# AODB is a database of working data (read-write). Mostly replaced by Redis.
TEMP_DIR = os.path.join(HOME_DIR, "db")

# Cache dir is for pickle dumps.
CACHE_DIR = os.path.join(TEMP_DIR, "cache")

# METAR storage directory
WEATHER_DIR = os.path.join(TEMP_DIR, "weather")

# Managed Airport storage directories
MANAGED_AIRPORT_DIR = os.path.join(DATA_DIR, "managedairport", MANAGED_AIRPORT_ICAO)
MANAGED_AIRPORT_AODB = os.path.join(TEMP_DIR, MANAGED_AIRPORT_ICAO)
MANAGED_AIRPORT_CACHE = os.path.join(
    CACHE_DIR, MANAGED_AIRPORT_ICAO
)  # os.path.join(MANAGED_AIRPORT_AODB, "cache")


# ######################
# Opera limits
#
AERODROME_PERIMETER_INDENTITY = "<orgId>:<classId>:<typeId>:<name>"


# ######################
# Database system-based Data
#
REDIS_CONNECT = {"host": "<redis-host>", "port": 6379, "db": 0}
REDIS_ATTEMPTS = 2
REDIS_WAIT = 1


# ######################
# Security (API-key)
# See https://github.com/mrtolkien/fastapi_simple_security
#
SECURE_API = True  # Whether to use api-key for all requests
ALLOW_KEYGEN = (
    True  # Whether to mount api to generate keys, should be false in production
)


# ######################
# Application options and parameters
#
# Broadcaster
BROADCASTER_HEARTBEAT = False
BROADCASTER_VERBOSE = True
BROADCASTER_TICK = 1000

# Sources of some data
METAR_HISTORICAL = False  # unreliable, limited, does not work
WEATHER = "GFS"  # or XP for X-Plane Real weather

# X-Plane location
XPLANE_DIR = os.path.join("<x-plane-home-directory>")
XPLANE_FEED = False
XPLANE_HOSTNAME = "<x-plane-host-ip-address>"
XPLANE_PORT = 49003
