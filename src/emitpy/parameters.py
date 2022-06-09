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
HOME_DIR = os.path.join("/Users", "pierre", "Developer", "py", "emitpy")  # should work even on windows... python guys are genius.

# DATA is a database of *static* data, definitions, etc. (read-only)
DATA_DIR = os.path.join(HOME_DIR, "data")
LOAD_AIRWAYS=False  # to speedup developments

# AODB is a database of working data (read-write). Mostly replaced by Redis
AODB_DIR = os.path.join(HOME_DIR, "db")


# ######################
# Database system-based Data
#
REDIS_CONNECT = {
    "host": "localhost",
    "port": 6379,
    "db": 0
}

DATA_IN_REDIS = True

SECURE_API = True
ALLOW_KEYGEN = True
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

BROADCASTER_HEARTBEAT = True

# Sources of some data
METAR_URL = "http://tgftp.nws.noaa.gov/data/observations/metar/stations"  # on window, don't you have to change / to \?
METAR_HISTORICAL = False

# X-Plane location
XPLANE_FEED = False

XPLANE_HOSTNAME = "Mac-mini-de-Pierre.local"
XPLANE_PORT = 49003
XPLANE_DIRECTORY = os.path.join("/Users", "pierre", "X-Plane 11")
