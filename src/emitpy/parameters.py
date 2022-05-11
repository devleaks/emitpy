"""
Application parameters not related to the simulation.
Used for file location, connection details, etc.
"""
import os



DEVELOPMENT = False  # produces additional debug if True
PRODUCTION = True  # removed caches and short circuits

# Should not be specified, should be deduced from Emitpy.__FILE__
HOME_DIR = os.path.join("/Users", "pierre", "Developer", "oscars", "emitpy")  # should work even on windows... python guys are genius.


# DATA is a database of *static* data, definitions, etc. (read-only)
DATA_DIR = os.path.join(HOME_DIR, "data")

LOAD_AIRWAYS=False  # to speedup developments


# AODB is a database of working data (read-write). Mostly replaced by Redis
AODB_DIR = os.path.join(HOME_DIR, "db")


# REDIS
USE_REDIS = True

REDIS_CONNECT = {
    "host": "localhost",
    "port": 6379,
    "db": 0
}

REDIS_COMMANDER_URL = "http://127.0.0.1:8081/"



# Mnaged Airport we are working on
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


# Default queues are created in emitpy if they do not exists.
# Must be in constants REDIS_QUEUE
DEFAULT_QUEUES = {
    "raw": "raw"
}

BROADCASTER_HEARTHBEAT = True

# Sources of some data
METAR_URL = "http://tgftp.nws.noaa.gov/data/observations/metar/stations"  # on window, don't you have to change / to \?
METAR_HISTORICAL = "https://www.ogimet.com"
