# Global application constants
#
from enum import Enum

SYSTEM_DIRECTORY = "."

########################################
# Identifiers (org,class,type,name)
#
# CLASSES
#
# 1. Vehicle
AIRCRAFT = "aircraft"
GSE = "gse"
CAR = "car"
BUS = "bus"
LORRY = "lorry"
TRUCK = "lorry"


# 2. Companies
AIRLINE = "airline"
TRANSPORTER = "transporter"
LOGISTICS = "logistics"
HANDLER = "handler"  # GSE, etc.



# 3. Airports (detailed and managed)
AIRLINES = "airlines"
AIRPORTS = "airports"
CONNECTIONS = "connections"
ROUTES = "routes"
PASSENGER = "pax"
CARGO = "cargo"

LOCAL = "local"
REMOTE = "remote"

#
# TYPES
#
# 1. load types
class PAYLOAD(Enum):
    PAX = "pax"
    CARGO = "cargo"
    TECH = "tech"
    PRIVATE = "priv"

# 2. freit type
BULK = "bulk"
PARCEL = "parcel"

# 3. GSE types
CLEANING = "clean"
CATERING = "catering"
FUEL = "fuel"
CARGO = "cargo"
BAGGAGE = "baggage"
MARSHALL = "marshall"
PUSHBACK = "pushback"
WATER = "water"


########################################
# Databases
AIRPORT_DATABASE = "airports"
AIRLINE_DATABASE = "airlines"
GEOMETRY_DATABASE = "geometries"
XPLANE_DATABASE = "x-plane"
AIRCRAFT_TYPE_DATABASE = "aircraft-types"
AIRCRAFT_DATABASE = "aircrafts"

MANAGED_AIRPORT = "managedairport"  # Home specific parameters and simulation parameters
FLIGHTROUTE_DATABASE = "flightplans"
AODB = "aodb"

########################################
# Keywords
class MOVEMENT(Enum):
    ARRIVAL = "arrival"
    DEPARTURE = "departure"


########################################
# Aeronautics constant
#
# ICAO Annex 14 - Aerodrome Reference Code Element 2, Table 1-1
# (Aeroplane Wingspan; Outer Main Gear Wheel Span)
# Code A - < 15m (49.2'); <4.5m (14.8')
# Code B - 15m (49.2') - <24m (78.7'); 4.5m (14.8') - <6m (19.7')
# Code C - 24m (78.7') - <36m (118.1'); 6m (19.7') - <9m (29.5')
# Code D - 36m (118.1') - <52m (170.6'); 9m (29.5') - <14m (45.9')
# Code E - 52m (170.6') - <65m (213.3'); 9m (29.5') - <14m (45.9')
# Code F - 65m (213.3') - <80m (262.5'); 14m (45.9') - <16m (52.5')
#
# X  WheelBase  WingSpan Example
# A 4.5m  15m Learjet 45, Baron etc, DC2 Beaver
# B 6m  24m DHC6 Twotter,
# C 9m  36m 737 NG / 737 , Q400, 300 ATR 72, A320 / E jet / Q400,300, F50
# D 14m 52m
# E 14m 65m Boeing 747 to 400 / A330/ 340 , 787-8 (DL)
# F 16m 80m 747_800, airbus
#
AIRCRAFT_TYPES = {  # Half width of taxiway in meters
    'A': 4,     # 7.5m
    'B': 6,     # 10.5m
    'C': 8,     # 15m or 18m
    'D': 9,     # 18m or 23m
    'E': 12,    # 23m
    'F': 15     # 30m
}


# X-Plane APT files constants
#
NODE_TYPE_BOTH = "both"
NODE_TYPE_DESTNATION = "dest"
NODE_TYPE_DEPART = "init"
NODE_TYPE_JUNCTION = "junc"

TAXIWAY_DIR_ONEWAY = "oneway"
TAXIWAY_DIR_TWOWAY = "twoway"

TAXIWAY_TYPE_TAXIWAY = "taxiway"
TAXIWAY_TYPE_RUNWAY = "runway"

TAXIWAY_ACTIVE_DEPARTURE = "departure"
TAXIWAY_ACTIVE_ARRIVAL = "arrival"
TAXIWAY_ACTIVE_ILS = "ils"


