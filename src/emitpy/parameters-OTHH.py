"""
Application parameters not related to the simulation.
Used for file location, connection details, etc.
"""
import os

DEVELOPMENT = True  # produces additional debug if True
PRODUCTION  = True  # removes caches and short circuits


# ######################
# Managed Airport we are working on
#
MANAGED_AIRPORT_ICAO = "OTHH"             # there is no default value
MANAGED_AIRPORT_OPERATOR = "MATAR"        # default is "AIRPORT_OPERATOR"
MANAGED_AIRPORT_HANDLER = "QAS"           # default is "AIRPORT_HANDLER"
MANAGED_AIRPORT_MISSION_HANDLER = "HIA"   # default is "MISSION_HANDLER"


# ######################
# File system-based Data
#
# Should not be specified, should be deduced from Emitpy.__FILE__
HOME_DIR = os.path.join("/Users", "pierre", "Developer", "oscars", "emitpy")  # should work even on windows... python guys are genius.

# DATA is a database of *static* data, definitions, etc. (read-only)
DATA_DIR = os.path.join(HOME_DIR, "data")

# AODB is a database of working data (read-write). Mostly replaced by Redis.
TEMP_DIR = os.path.join(HOME_DIR, "db")

# Cache dir is for pickle dumps.
CACHE_DIR = os.path.join(TEMP_DIR, "cache")

# METAR storage directory
METAR_DIR = os.path.join(TEMP_DIR, "metar")

# Managed Airport database folders
MANAGED_AIRPORT_DIR  = os.path.join(DATA_DIR, "managedairport", MANAGED_AIRPORT_ICAO)
MANAGED_AIRPORT_AODB = os.path.join(TEMP_DIR, MANAGED_AIRPORT_ICAO)
MANAGED_AIRPORT_CACHE = os.path.join(CACHE_DIR, MANAGED_AIRPORT_ICAO)  # os.path.join(MANAGED_AIRPORT_AODB, "cache")


# ######################
# Database system
#
REDIS_CONNECT = {
    "host": "localhost",
    "port": 6379,
    "db": 0
}
REDIS_ATTEMPTS = 2
REDIS_WAIT = 1

# ######################
# Security (API-key)
# See https://github.com/mrtolkien/fastapi_simple_security
#
SECURE_API = False
ALLOW_KEYGEN = False


# ######################
# Application options and parameters
#
# Broadcaster
BROADCASTER_HEARTBEAT = False
BROADCASTER_VERBOSE = True
BROADCASTER_TICK = 1000

# Sources of some data
METAR_HISTORICAL = False  # unreliable, limited, does not work

# X-Plane location
XPLANE_DIR = os.path.join(DATA_DIR, "x-plane") # os.path.join("/Users", "pierre", "X-Plane 11")
XPLANE_FEED = False
XPLANE_HOSTNAME = "Mac-mini-de-Pierre.local"
XPLANE_PORT = 49005   # aitfc, rttfc => LiveTraffic 49005, xpplanes => XPPlanes 49800 (broadcast)
