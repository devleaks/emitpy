"""
Application parameters not related to the simulation.
Used for file location, connection details, etc.
"""
import os

DEVELOPMENT = True  # produces additional debug
PRODUCTION = False  # removed caches and short circuits

HOME_DIR = "."

# DATA is a database of static data, definitions, etc.
DATA_DIR = os.path.join(HOME_DIR, "..", "data")

# AODB is a database of working data
AODB_DIR = os.path.join(HOME_DIR, "..", "db")


AIRCRAFT_TYPE_DATABASE = "aircraft"

METAR_URL = "http://tgftp.nws.noaa.gov/data/observations/metar/stations"

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
    "tzname": "Doha"
}

LOAD_AIRWAYS=False  # to speedup developments

# Default queues are created in emitpy if they do not exists.
DEFAULT_QUEUES = {
    "lt": "lt",
    "raw": "raw"
}

