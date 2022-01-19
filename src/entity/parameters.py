"""
Global parameters for application
"""
import os

HOME_DIR = "."

# DATA is a database of static data, definitions, etc.
DATA_DIR = os.path.join(HOME_DIR, "..", "data")

# AODB is a database of working data
AODB_DIR = os.path.join(HOME_DIR, "..", "data", "_db")


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
    "lon": 51.6077
}
