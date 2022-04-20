"""
Application parameters not related to the simulation.
Used for file location, connection details, etc.
"""
import os

DEVELOPMENT = True  # produces additional debug
PRODUCTION = False  # removed caches and short circuits

HOME_DIR = os.path.join(".", "..")

# DATA is a database of static data, definitions, etc.
DATA_DIR = os.path.join(HOME_DIR, "data")

# AODB is a database of working data
AODB_DIR = os.path.join(HOME_DIR, "db")

METAR_URL = "http://tgftp.nws.noaa.gov/data/observations/metar/stations"
METAR_HISTORICAL_URL = ""

MANAGED_AIRPORT = {
    "ICAO": "OTHH",
    "IATA": "DOH",
    "name": "Hamad International Airport",
    "city": "Doha",
    "country": "Qatar",
    "regionName": "Qatar",
    "elevation": 13.000000019760002,
    "lat": 25.2745,
    "lon": 51.6077,
    "tzoffset": 3,
    "tzname": "Doha",
    "operator": "MATAR"
}

LOAD_AIRWAYS=False  # to speedup developments

REDIS_CONNECT = {
    "host": "localhost",
    "port": 6379,
    "db": 0
}

# REDIS stuff if not on same host


# Default queues are created in emitpy if they do not exists.
DEFAULT_QUEUES = {
    "lt": "lt",
    "raw": "raw"
}

