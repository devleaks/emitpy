# Application constants and global parameters related to the simulation
#
from enum import Enum, IntEnum, Flag


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
class PAYLOAD(Flag):
    PAX = "pax"
    CARGO = "cargo"
    TECH = "tech"
    PRIVATE = "priv"

# 2. freit type
BULK = "bulk"
PARCEL = "parcel"


# 3. GSE types
class SERVICE(Enum):
    CLEANING = "cleaning"
    CATERING = "catering"
    FUEL = "fuel"
    CARGO = "cargo"
    ULD = "uld"
    BAGGAGE = "baggage"
    MARSHALL = "marshall"
    PUSHBACK = "pushback"
    WATER = "water"
    APU = "apu"
    SEWAGE = "sewage"
    STANDBY = "standby"

class SERVICE_COLOR(Enum):
    CLEANING = "#eeeeee"
    CATERING = "#ffff66"
    FUEL = "#FF66DD"
    CARGO = "#330099"
    ULD = "#9933FF"
    BAGGAGE = "#009999"
    MARSHALL = "#FFFF00"
    PUSHBACK = "#FF3333"
    WATER = "#0066FF"
    APU = "#FFCC00"
    SEWAGE = "#333300"
    STANDBY = "#AAAAAA"


########################################
# Databases
AIRPORT_DATABASE = "airports"
AIRLINE_DATABASE = "airlines"
GEOMETRY_DATABASE = "geometries"
XPLANE_DATABASE = "x-plane"
AIRCRAFT_TYPE_DATABASE = "aircraft-types"
AIRCRAFT_DATABASE = "aircrafts"
FLIGHT_DATABASE = "flights"
METAR_DATABASE = "metar"

MANAGED_AIRPORT = "managedairport"  # Home specific parameters and simulation parameters
FLIGHTROUTE_DATABASE = "flightplans"
AODB = "aodb"


########################################
# Aeronautics-related constant
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

AICRAFT_DEFAULT = "AIRBUS"  # alt: "BOEING"

# X-Plane APT files keywords and constants
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


# @todo: Should distinguish "points" (top_of_descent) and "phases" ("climb")
class FLIGHT_PHASE(Enum):
    OFFBLOCK = "OFFBLOCK"
    PUSHBACK = "PUSHBACK"
    TAXI = "TAXI"
    TAXIHOLD = "TAXIHOLD"  # just before entering the runway
    TAKEOFF_HOLD = "TAKEOFF_HOLD"  # on the runways
    TAKE_OFF = "TAKE_OFF"
    TAKEOFF_ROLL = "TAKEOFF_ROLL"
    ROTATE = "ROTATE"
    LIFT_OFF = "LIFT_OFF"
    INITIAL_CLIMB = "INITIAL_CLIMB"
    CLIMB = "CLIMB"
    CRUISE = "CRUISE"
    DESCEND = "DESCEND"
    HOLDING = "HOLDING"
    APPROACH = "APPROACH"
    FINAL = "FINAL"
    LANDING = "LANDING"
    FLARE = "FLARE"
    TOUCH_DOWN = "TOUCH_DOWN"
    ROLL_OUT = "ROLL_OUT"
    END_ROLLOUT = "END_ROLLOUT"
    STOPPED_ON_RWY = "STOPPED_ON_RWY"
    RUNWAY_EXIT = "RUNWAY_EXIT"
    STOPPED_ON_TAXIWAY = "STOPPED_ON_TAXIWAY"
    PARKING = "PARKING"
    ONBLOCK = "ONBLOCK"
    SCHEDULED = "SCHEDULED"
    TERMINATED = "TERMINATED"
    CANCELLED = "CANCELLED"
    TOWED = "TOWED"
    UNKNOWN = "UNKNOWN"
    TOP_OF_ASCENT = "TOP_OF_ASCENT"
    TOP_OF_DESCENT = "TOP_OF_DESCENT"


class MISSION_PHASE(Enum):
    START = "start"
    CHECKPOINT = "checkpoint"
    EN_ROUTE = "enroute"
    END = "end"

class MISSION_COLOR(Enum):
    START = "#00dd00"
    CHECKPOINT = "#0000dd"
    EN_ROUTE = "#eeeeee"
    END = "#dd0000"

class SERVICE_PHASE(Enum):
    START = "start"
    ARRIVED = "arrived"
    SERVICE_START = "service-start"
    SERVICE_END = "service-end"
    LEAVE = "leave"
    END = "end"

class SERVICE_PHASE_COLOR(Enum):
    START = "#008800"
    ARRIVED = "#00dd00"
    SERVICE_START = "#0000dd"
    SERVICE_END = "#000088"
    LEAVE = "#dd0000"
    END = "#880000"

# geojson.io color for point and linestring features
#
class FLIGHT_COLOR(Enum):
    OFFBLOCK = "#990000"
    PUSHBACK = "#FF0000"
    TAXI = "#FF3300"
    TAXIHOLD = "#CC3300"
    TAKEOFF_HOLD = "#FF66D0"
    TAKE_OFF = "#0033CC"
    TAKEOFF_ROLL = "#FF9900"
    ROTATE = "#FFCC00"
    LIFT_OFF = "#FFFF00"
    INITIAL_CLIMB = "#FFFF00"
    CLIMB = "#CCFF00"
    CRUISE = "#00FFFF"
    DESCEND = "#006699"
    APPROACH = "#0066CC"
    FINAL = "#0000FF"
    LANDING = "#00CC00"
    FLARE = "#339900"
    TOUCH_DOWN = "#339900"
    ROLL_OUT = "#330066"
    STOPPED_ON_RWY = "#6600CC"
    RUNWAY_EXIT = "#9900FF"
    STOPPED_ON_TAXIWAY = "#CC00FF"
    PARKING = "#CC00CC"
    ONBLOCK = "#FF00FF"
    SCHEDULED = "#3399FF"
    TERMINATED = "#0066CC"
    CANCELLED = "#FF9900"
    TOWED = "#CCCCCC"
    UNKNOWN = "#666666"
    TOP_OF_ASCENT = "#DDDD00"
    TOP_OF_DESCENT = "#00DDDD"


class POSITION_COLOR(Enum):
    PUSHBACK = "#FF0000"
    TAXI = "#FF3300"
    TAXIHOLD = "#CC3300"
    TAKEOFF_HOLD = "#FF66D0"
    TAKE_OFF = "#0033CC"
    TAKEOFF_ROLL = "#0033CC"
    ROTATE = "#FFCC00"
    LIFT_OFF = "#FFFF00"
    INITIAL_CLIMB = "#FFFF00"
    CLIMB = "#CCFF00"
    CRUISE = "#00FFFF"
    DESCEND = "#006699"
    APPROACH = "#0066CC"
    FINAL = "#0000FF"
    LANDING = "#00CC00"
    FLARE = "#339900"
    TOUCH_DOWN = "#339900"
    ROLL_OUT = "#330066"
    STOPPED_ON_RWY = "#6600CC"
    RUNWAY_EXIT = "#9900FF"
    STOPPED_ON_TAXIWAY = "#CC00FF"
    PARKING = "#CC00CC"
    ONBLOCK = "#FF00FF"
    SCHEDULED = "#3399FF"
    TERMINATED = "#0066CC"
    CANCELLED = "#FF9900"
    TOWED = "#CCCCCC"
    RUNWAY_THRESHOLD = "#666666"
    DEPARTURE = "#FFFF00"
    ORIGIN = "#FFFF00"
    ARRIVAL = "#FF6600"
    DESTINATION = "#FF6600"
    TOP_OF_ASCENT = "#00FF00"
    TOP_OF_DESCENT = "#0000FF"
    HOLDING = "#AAAAFF"
    FLIGHT_PLAN = "#880000"


class EDGE_COLOR(Enum):
    TAXIWAY_ONEWAY = "#666666"
    TAXIWAY_TWOWAY = "#666666"
    TAXIWAY = "#666666"
    SERVICE_ROAD_ONEWAY = "#666666"
    SERVICE_ROAD_TWOWAY = "#666666"
    SERVICE_ROAD = "#666666"
    JETWAY_HI = "#666666"
    JETWAY_LO = "#666666"
    JETWAY_VICTOR = "#666666"
    JETWAY_JULIET = "#666666"
    STAR = "#666666"
    SID = "#666666"
    APPCH = "#666666"
    RUNWAY = "#666666"


class FEATPROP(Enum):
    # Feature property names
    NAME = "name"
    MARK = "_mark"
    ALTITUDE = "altitude"
    SPEED = "speed"
    VSPEED = "vspeed"
    VERTICAL_SPEED = "vspeed"
    HEADING = "heading"
    TIME = "time"
    PAUSE = "pause"
    DELAY = "delay"  # was pause in emitjs
    FLIGHT_PLANDB_INDEX = "fpdb-index"
    FLIGHT_PLAN_INDEX = "plan-index"
    MOVE_INDEX = "move-index"
    MOVEST_INDEX = "move-st-index"
    POI_TYPE = "poi-type"
    RUNWAY = "runway"
    SERVICE = "service"
    STOP_TIME = "stop-time"
    BROADCAST = "broadcast"
    EMIT_INDEX = "emit-index"
    EMIT_REASON = "emit-reason"
    EMIT_REL_TIME = "emit_relative_time"
    EMIT_ABS_TIME = "emit_absolute_time"
    CONTROL_TIME = "control-time"


class FILE_EXT(Enum):
    FLIGHT_PLAN = "1-plan"
    FLIGHT = "2-flight"
    SERVICE = "3-service"
    MOVE = "3-move"
    EMIT = "4-emit"
    BROADCAST = "5-broadcast"


class REDIS_DATABASE(Enum):
    FLIGHTS = "flights"
    MOVEMENTS = "movements"
    QUEUES = "queues"


class REDIS_TYPE(Enum):
    EMIT = ":e"
    EMIT_META = ":m"
    EMIT_KML = ":k"
    FORMAT = ":f"
    QUEUE = ":q"


class REDIS_QUEUE(Enum):
    ADMIN_QUEUE_PREFIX = "queues"
    ADSB = "adsb"
    LIVETRAFFIC = "lt"
    RAW = "raw"
    DEFAULT = "raw"


class POI_TYPE(Enum):
    # Feature property names
    RUNWAY_EXIT = "runway-exit"
    TAKEOFF_QUEUE = "takeoff-queue"  # lineString
    DEPOT = "depot"
    REST_AREA = "rest-area"
    RAMP_SERVICE_POINT = "ramp-service-point"
    QUEUE_POSITION = "toq-pos"


class RAMP_TYPE(Enum):
    GATE = "gate"
    TIE_DOWN = "tie-down"
    HANGAR = "hangar"


class ARRIVAL_DELAY(IntEnum):
    # Feature property names
    HOLDING = 0
    STAND_BYSU = 1


class DEPARTURE_DELAY(IntEnum):
    # Feature property names
    PUSHBACK = 0
    TAXI = 1
    RUNWAY_HOLD = 2
    TAKEOFF_QUEUE = 3
    TAKEOFF_HOLD = 4

TAG_SEP = "|"
ID_SEP = ":"

# Simulation
#
TAKEOFF_QUEUE_SIZE = 1

TAXI_SPEED = 10  # 10m/s = 36km/h = taxi speed
SLOW_SPEED = 1.4 # 1.4m/s = 5km/h = slow speed

EMIT_RATES = [(str(x), str(x)) for x in [1, 5, 10, 30, 60, 120, 300]]
RATE_LIMIT = 10       # Maximum frequency when range of emission is limited to managed airport
EMIT_RANGE = None     # Maximum range of emission when rate under RATE_LIMIT

