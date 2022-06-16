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
LOAD_AIRWAYS=False  # to speedup developments

# AODB is a database of working data (read-write). Mostly replaced by Redis
AODB_DIR = os.path.join(HOME_DIR, "db")


# ######################
# Database system-based Data
#
REDIS_CONNECT = {
    "host": "<redis-host>",
    "port": 6379,
    "db": 0
}

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

BROADCASTER_HEARTBEAT = False

# Sources of some data
METAR_URL = "http://tgftp.nws.noaa.gov/data/observations/metar/stations"
METAR_HISTORICAL = False

# X-Plane location
XPLANE_FEED = False

XPLANE_HOSTNAME = "<x-plane-host-ip-address>"
XPLANE_PORT = 49003
XPLANE_DIR = os.path.join("<x-plane-home-directory>")
