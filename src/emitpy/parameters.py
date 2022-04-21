"""
Application parameters not related to the simulation.
Used for file location, connection details, etc.
"""
import os

DEVELOPMENT = False  # produces additional debug
PRODUCTION = True  # removed caches and short circuits

HOME_DIR = os.path.join("/", "app")  # should work even on windows... python guys are genius.

# DATA is a database of static data, definitions, etc.
DATA_DIR = os.path.join(HOME_DIR, "data")

# AODB is a database of working data
AODB_DIR = os.path.join(HOME_DIR, "db")


METAR_URL = "http://tgftp.nws.noaa.gov/data/observations/metar/stations"  # on window, don't you have to change / to \?

MANAGED_AIRPORT = {
    "ICAO": "OTHH",
    "IATA": "DOH",
    "name": "Hamad International Airport",
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

# Default queues are created in emitpy if they do not exists.
DEFAULT_QUEUES = {
    "raw": "raw"
}

# REDIS stuff if not on same host
REDIS_CONNECT = {
    "host": "redis",
    "port": 6379,
    "db": 0
}

LOAD_AIRWAYS=True  # to speedup developments

