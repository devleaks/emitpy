"""
Application parameters not related to the simulation.
Used for file location, connection details, etc.
"""
import os

DEVELOPMENT = False  # produces additional debug
PRODUCTION = True  # removed caches and short circuits

HOME_DIR = "/app"

# DATA is a database of static data, definitions, etc.
DATA_DIR = os.path.join(HOME_DIR, "data")

# AODB is a database of working data
AODB_DIR = os.path.join(HOME_DIR, "db")


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

REDIS_CONNECT = {
    "host": "redis",
    "port": 6379,
    "db": 0
}

LOAD_AIRWAYS=True  # to speedup developments