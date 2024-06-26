# Application constants and global parameters related to the simulation
#
from enum import Enum, IntEnum

########################################
# Identifiers (org,class,type,name)
#
# CLASSES
#
# 1. Vehicle
AIRCRAFT = "aircraft"
GSE = "gse"
# CAR = "car"
# BUS = "bus"
# LORRY = "lorry"
# TRUCK = "lorry"


# 2. Companies
AIRLINE = "airline"
FLIGHT_OPERATOR = "flight-operator"

# TRANSPORTER = "transporter"
# LOGISTICS = "logistics"
HANDLER = "handler"  # GSE, etc.
OPERATOR = "operator"  # GSE, etc.


# 3. Airports (detailed and managed)
AIRLINES = "airlines"
AIRPORTS = "airports"
ROUTES = "routes"

PASSENGER = "pax"
CARGO = "cargo"

# Aircraft performances
LOW_ALT_MAX_SPEED = 250  # kn
LOW_ALT_ALT_FT = 10000  # ft

# Navigation
FT = 12 * 0.0254
INITIAL_CLIMB_SAFE_ALT_M = 1500 * FT
FINAL_APPROACH_FIX_ALT_M = 2000 * FT


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
class SERVICE(Enum):
    PASSENGER = "passenger"
    CLEANING = "cleaning"
    SEWAGE = "sewage"
    CATERING = "catering"
    WATER = "water"
    FUEL = "fuel"
    CARGO = "cargo"
    BAGGAGE = "baggage"
    AIRCRAFT = "aircraft"


########################################
# File databases
#
DATA = "data"  # root data dir
AODB = "db"  # root AODB dir


class AODB_DIRECTORIES(Enum):
    FLIGHTS = "flights"
    MISSIONS = "missions"
    SERVICES = "services"
    MOVEMENTS = "moves"
    METAR = "metar"
    DEBUG = "debug"


MANAGED_AIRPORT_KEY = "managed"
MANAGED_AIRPORT_LAST_UPDATED = "last-updated"

# Sub-dirs of above "root" dirs
AIRCRAFT_DATABASE = "aircrafts"
AIRCRAFT_TYPE_DATABASE = "aircraft_types"
AIRLINE_DATABASE = "airlines"
AIRPORT_DATABASE = "airports"
FLIGHT_DATABASE = "flights"
FLIGHTROUTE_DATABASE = "flightplans"
MANAGED_AIRPORT = "managedairport"  # Home specific parameters and simulation parameters
METAR_DATABASE = "metar"
MESSAGE_DATABASE = "messages"
MOVES_DATABASE = "moves"
SERVICE_VEHICLE_TYPE_DATABASE = "equipment_types"
XPLANE_DATABASE = "x-plane"

# sub-sub dirs
GEOMETRY_DATABASE = "geometries"


# Misc Keywords
SCHEDULED = "scheduled"
ESTIMATED = "estimated"
ACTUAL = "actual"
TERMINATED = "terminated"


ID_SEP = ":"
ID_SEP_ALT = "-"
TAG_SEP = "|"
FLIGHT_TIME_FORMAT = "%Y%m%d%H%M"
AIRAC_CYCLE = "AIRAC"

DEFAULT_VEHICLE = ":def"
DEFAULT_VEHICLE_SHORT = "std"
DEFAULT_VEHICLE_ICAO = "ZZZC"  # marshall car


class POI_COMBO(Enum):
    RAMP = "ramp"
    SERVICE = "svc"
    CHECKPOINT = "ckpt"


class FILE_FORMAT(Enum):
    FLIGHT_PLAN = "1-plan"
    SO6 = "1-so6"  # Flight plan in Eurocontrol SO6 format
    FLIGHT = "2-flight"
    SERVICE = "3-service"
    MOVE = "3-move"
    TAXI = "4-taxi"
    EMIT = "5-emit"
    BROADCAST = "6-broadcast"
    MESSAGE = "7-messages"
    KML = "9-kml"
    TRAFFIC = "9-traffic"


########################################
# Redis databases and keys
#
# Redis key builder with domains
#
def key_path(*args):  # difficult to "import" without circular issues
    a = map(lambda x: x if x is not None else "", args)
    return ID_SEP.join(a)


# "Categories" of data stored, used as domain separator
class REDIS_DATABASE(Enum):
    ALLOCATIONS = "airport"
    AIRCRAFTS = "aircrafts"
    FLIGHTS = "flights"
    MESSAGES = "messages"
    METAR = "metar"
    MISSIONS = "missions"
    MOVEMENTS = "movements"
    QUEUES = "queues"  # Note: Used both as a key and as a pubsub queue name for internal queue management
    SERVICES = "services"
    COMPAGNIES = "company-directory"
    PEOPLE = "directory"
    LOVS = "lovs"
    EMIT_METAS = "emit-meta"
    UNKNOWN = "unknowndb"


class REDIS_DB(IntEnum):
    APP = 0  # App data, dynamic
    REF = 1  # App data, static
    CACHE = 2  # Real temp cache
    PERM = 3  # Permanent (METAR, etc.)


class EMIT_TYPE(Enum):
    FLIGHT = "flight"
    MISSION = "mission"
    SERVICE = "service"


REDIS_DATABASES = {
    "allocation": REDIS_DATABASE.ALLOCATIONS.value,
    "flight": REDIS_DATABASE.FLIGHTS.value,
    "message": REDIS_DATABASE.MESSAGES.value,
    "metar": REDIS_DATABASE.METAR.value,
    "mission": REDIS_DATABASE.MISSIONS.value,
    "service": REDIS_DATABASE.SERVICES.value,
    "unknowndb": REDIS_DATABASE.UNKNOWN.value,  # should be symmetric to avoid issues
}


# Type of data stored into keys
class REDIS_TYPE(Enum):
    EMIT = "e"
    EMIT_META = "d"
    EMIT_MESSAGE = "m"
    EMIT_KML = "k"
    FORMAT = "f"
    QUEUE = "q"


# Type of data stored into keys
class REDIS_LOVS(Enum):
    AIRCRAFT_TYPES = "aircrafts"
    AIRPORTS = "airports"
    AIRLINES = "airlines"
    RAMPS = key_path("airport", "ramps")
    RUNWAYS = key_path("airport", "runways")
    POIS = key_path("airport", "pois")
    COMPANIES = key_path("airport", "companies")
    MANAGED_AIRPORTS = "managed-airports"


class REDIS_PREFIX(Enum):
    AEROWAYS = "aeroways"
    AIRWAYS = "aeroways"
    AIRCRAFT_EQUIS = key_path("aircraft", "equivalences")
    AIRCRAFT_PERFS = key_path("aircraft", "performances")
    AIRCRAFT_TARPROFILES = key_path("aircraft", "service-profiles")
    AIRCRAFT_GSEPROFILES = key_path("aircraft", "gse-profiles")
    AIRCRAFT_TYPES = key_path("aircraft", "types")
    AIRLINE_ROUTES = key_path("business", "airroutes", "airlines")
    AIRLINES = key_path("business", "airlines")
    AIRLINE_NAMES = key_path("business", "airline_names")
    AIRPORT = "airport"
    AIRPORT_ROUTES = key_path("business", "airroutes", "airports")
    AIRPORTS = "airports"
    AIRPORTS_GEO_INDEX = key_path("airports", "_geo_index")
    AIRPORT_GEO_INDEX = key_path("airport", "_geo_index")
    AIRSPACE = "airspace"
    AIRSPACE_CONTROLLED = key_path("airspace", "controlled-airspaces")
    AIRSPACE_AIRWAYS = key_path("airspace", "airways")
    AIRSPACE_ALL_INDEX = key_path("airspace", "idents")
    # AIRSPACE_FIXES = key_path("airspace", "fixes")
    # AIRSPACE_FIXES_INDEX = key_path("airspace", "fixes", "_index")
    # AIRSPACE_GEO_INDEX = key_path("airspace", "_geo_index")
    AIRSPACE_HOLDS = key_path("airspace", "holds")
    AIRSPACE_HOLDS_GEO_INDEX = key_path("airspace", "holds", "_geo_index")
    # AIRSPACE_NAVAIDS = key_path("airspace", "navaids")
    # AIRSPACE_NAVAIDS_INDEX = key_path("airspace", "navaids", "_index")
    # AIRSPACE_RESTRICTIONS = key_path("airspace", "restrictions")
    AIRSPACE_TERMINALS = key_path("airspace", "terminals")
    AIRSPACE_WAYPOINTS_GEO_INDEX = key_path("airspace", "waypoints", "_geo_index")
    AIRSPACE_WAYPOINTS_INDEX = key_path("airspace", "waypoints", "_index")
    AIRSPACE_WAYPOINTS = key_path("airspace", "waypoints")
    BUSINESS = "business"
    COMPANIES = key_path("business", "companies")
    FLIGHTPLAN_APTS = key_path(FLIGHTROUTE_DATABASE, "airports")
    FLIGHTPLAN_FPDB = key_path(FLIGHTROUTE_DATABASE, "fpdb")
    FLIGHTPLAN_GEOJ = key_path(FLIGHTROUTE_DATABASE, "geojson")
    GEOJSON = "geojson"
    GROUNDSUPPORT = "service"
    GROUNDSUPPORT_DESTINATION = "service-destination"
    GSE = key_path("airport", "gse")
    IATA = "iata"
    ICAO = "icao"
    MISSION = "mission"
    RAMPS = "ramps"
    RUNWAYS = "runways"
    TAR_PROFILES = key_path("business", "turnaround-profiles")
    GSE_PROFILES = key_path("business", "ramp-gse-profiles")


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
AIRCRAFT_CLASSES = {  # Half width of taxiway in meters
    "A": 4,  # 7.5m
    "B": 6,  # 10.5m
    "C": 8,  # 15m or 18m
    "D": 9,  # 18m or 23m
    "E": 12,  # 23m
    "F": 15,  # 30m
}

AICRAFT_DEFAULT = "AIRBUS"  # {"AIRBUS","BOEING"}

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


########################################
# Movements and Emissions or positions
#
# @todo: Should distinguish "points" (top_of_descent) and "phases" ("climb")
ARRIVAL = "arrival"
DEPARTURE = "departure"

RWY_DEPARTURE_SLOT = 180  # seconds
RWY_ARRIVAL_SLOT = 180  # seconds (note: possible issues if not symmetric)


# Type of data stored into files
class MOVE_TYPE(Enum):
    FLIGHT = "flight"
    SERVICE = "service"
    MISSION = "mission"


class FLIGHT_SEGMENT(Enum):
    RWYDEP = "rwydep"
    RWYARR = "rwyarr"
    SID = "sid"
    STAR = "star"
    APPCH = "appch"
    CRUISE = "cruise"


class FLIGHT_PHASE(Enum):
    OFFBLOCK = "OFFBLOCK"
    PUSHBACK = "PUSHBACK"
    TAXI = "TAXI"
    TAXI_OUT = "TAXI-OUT"
    TAXIHOLD = "TAXIHOLD"  # just before entering the runway
    TAKE_OFF_HOLD = "TAKE_OFF_HOLD"  # on the runways
    TAKE_OFF = "TAKE_OFF"
    TAKE_OFF_ROLL = "TAKE_OFF_ROLL"
    ROTATE = "ROTATE"
    LIFT_OFF = "LIFT_OFF"
    INITIAL_CLIMB = "INITIAL_CLIMB"  # =BEGIN_DEP_RESTRICTIONS
    ACCELERATE = "ACCELERATE"
    END_DEPARTURE_RESTRICTIONS = "END_DEP_RESTRICTION"
    CLIMB = "CLIMB"
    TOP_OF_ASCENT = "TOP_OF_ASCENT"
    CRUISE = "CRUISE"
    BEGIN_ARRIVAL_RESTRICTIONS = "END_ARR_RESTRICTION"  # = END_OF_CRUISE
    LEAVE_CRUISE_SPEED = "LEAVE_CRUISE_SPEED"
    TOP_OF_DESCENT = "TOP_OF_DESCENT"
    DESCEND = "DESCEND"
    FAR_AWAY = "100MO"
    HOLDING = "HOLDING"
    TEN_MILE_OUT = "TMO"
    APPROACH = "APPROACH"
    DECELERATE = "DECELERATE"
    INITIAL_FIX = "INITIAL_FIX"
    FINAL = "FINAL"
    FINAL_FIX = "FINAL_FIX"  # =END_ARRIVAL_RESTRICTIONS
    LANDING = "LANDING"
    FLARE = "FLARE"
    TOUCH_DOWN = "TOUCH_DOWN"
    ROLL_OUT = "ROLL_OUT"
    END_ROLLOUT = "END_ROLLOUT"
    STOPPED_ON_RWY = "STOPPED_ON_RWY"
    RUNWAY_EXIT = "RUNWAY_EXIT"
    STOPPED_ON_TAXIWAY = "STOPPED_ON_TAXIWAY"
    TAXI_IN = "TAXI-IN"
    PARKING = "PARKING"
    ONBLOCK = "ONBLOCK"
    SCHEDULED = "SCHEDULED"
    TERMINATED = "TERMINATED"
    CANCELLED = "CANCELLED"
    TOWED = "TOWED"
    UNKNOWN = "UNKNOWN"


ARRIVAL_TIME = FLIGHT_PHASE.TOUCH_DOWN.value  # {TOUCH_DOWN|ONBLOCK}
DEPARTURE_TIME = FLIGHT_PHASE.TAKE_OFF.value  # {OFFBLOCK|TAKE_OFF_HOLD|TAKE_OFF}


class MISSION_PHASE(Enum):
    START = "start"
    CHECKPOINT = "checkpoint"
    EN_ROUTE = "enroute"
    END = "end"


EVENT_ONLY_MESSAGE = "event"
EVENT_ONLY_SERVICE = "EventService"


# Keywords found in ta_profiles
class TAR_SERVICE(Enum):
    TYPE = "type"
    START = "start"
    DURATION = "duration"
    ALERT = "alert"
    WARN = "warn"
    MODEL = "model"
    LABEL = "event"
    EVENT = "event"
    QUANTITY = "quantity"


# Keywords found in ta_profiles
class EQUIPMENT(Enum):
    TYPE = "type"
    COUNT = "fleet"
    MODEL = "model"
    LABEL = "event"
    QUANTITY = "fleet"
    CAPACITY = "capacity"
    FLOW = "flow"
    CLEANUP = "cleanup-time"
    SETUP = "setup-time"


class SERVICE_PHASE(Enum):
    START = "start"
    ARRIVED = "arrived"
    SERVICE_START = "service-start"
    SERVICE_END = "service-end"
    LEAVE = "leave"
    END = "end"
    OCCURRED = "occurred"  # when an event-type service happens


class POI_TYPE(Enum):
    # Feature property names
    RUNWAY_EXIT = "runway-exit"
    TAKE_OFF_QUEUE = "takeoff-queue"  # lineString
    DEPOT = "depot"
    REST_AREA = "rest-area"
    RAMP_SERVICE_POINT = "ramp-service-point"
    QUEUE_POSITION = "toq-pos"
    # Added for compatibility with X-Plane (special vocabulary)
    DESTINATION = "destination"
    PARKING = "parking"


QUEUE_GAP = 200  # meters


class RAMP_TYPE(Enum):
    JETWAY = "jetway"
    TIE_DOWN = "tiedown"


#   HANGAR = "hangar"


class ARRIVAL_DELAY(IntEnum):
    HOLDING = 0
    STAND_BYSU = 1


class DEPARTURE_DELAY(IntEnum):
    PUSHBACK = 0
    TAXI = 1
    RUNWAY_HOLD = 2
    TAKE_OFF_QUEUE = 3
    TAKE_OFF_HOLD = 4


########################################
# Feature properties
#
class FEATPROP(Enum):
    # Feature property names
    AIRSPACES = "airspaces"
    ALTITUDE = "altitude"
    BROADCAST = "broadcast"
    CITY = "city"
    CLASS = "class"
    CLASS_ID = "classId"
    COMMENT = "comment"
    CONTROL_TIME = "control-time"
    COUNTRY = "country"
    COURSE = "course"  # direction in which goes the aircraft, sometimes called TRACK or TRACKING
    DELAY = "delay"  # was pause in emitjs
    EMIT_ABS_TIME = "emit-absolute-time"
    EMIT_ABS_TIME_FMT = "emit-absolute-time-human"
    EMIT_ABSOLUTE_TIME = "emit-absolute-time"
    EMIT_ABSOLUTE_TIME_FMT = "emit-absolute-time-human"
    EMIT_FORMAT = "emit-format"
    EMIT_INDEX = "emit-index"
    EMIT_REASON = "emit-reason"
    EMIT_REL_TIME = "emit-relative-time"
    EMIT_RELATIVE_TIME = "emit-relative-time"
    FLIGHT_MOVE_INDEX = "move-index"
    FLIGHT_PLAN_INDEX = "plan-index"
    FLIGHT_PLAN_TIME = "plan-time"
    GROUND_ALT = "GLOBE-ground-altitude"
    TAXI_INDEX = "taxi-index"
    JETWAY = "jetway"
    GROUNDED = "grounded"
    HEADING = "heading"  # direction in which point the aircraft
    ICAO24 = "icao24"
    LINE = "line"
    MARK = "_mark"
    MARK_SEQUENCE = "_mark-seq"
    MESSAGE_ID = "message-id"
    MISSION = "mission"
    MOVE_INDEX = "move-index"  # after standard turns added, smoothing, etc.
    NAME = "name"
    ORG_ID = "orgId"
    ORIENTATION = "orientation"  # direction in which point the aircraft, synonym of HEADING, used for ground vehicle
    PAUSE = "pause"
    PLAN_SEGMENT_NAME = "_plan_segment_name"
    PLAN_SEGMENT_TYPE = "_plan_segment_type"
    POI_TYPE = "poi-type"
    POI_SERVICE = "poi-service"
    PREMOVE_INDEX = "pre-move-index"  # pre-move is flight plan + vnav, without smoothing, timing, etc.
    REGION = "region"
    RESTRICTION = "restriction"
    RUNWAY = "runway"
    SAVED_TIME = "saved-time"
    SERVICE = "service"
    SERVICE_TYPE = "service-type"  # ~ SERVICE?
    SPEED = "speed"  # ground speed
    TASPEED = "true-air-speed"  # TAS
    STOP_TIME = "stop-time"
    TIME = "time"
    TYPE_ID = "typeId"
    VERSION = "emitpy-version"
    VERTICAL_SPEED = "vspeed"
    VSPEED = "vspeed"
    WIND = "_wind"


########################################
# Simulation
#
TAKE_OFF_QUEUE_SIZE = 4  # DO NOT CHANGE

# Average default speeds
TAXI_SPEED = 10  # 10m/s = 36km/h = taxi speed
SLOW_SPEED = 1.4  # 1.4m/s = 5km/h = slow speed

# Point emission limit and control
EMIT_RATES = [(str(x), str(x)) for x in (list(range(31)) + [60, 120, 300, 600, 900, 1200, 1800, 3600])]  # possible values
RATE_LIMIT = 10  # Maximum frequency when range of emission is limited to managed airport
EMIT_RANGE = 5  # Maximum range (in kilometers) of emission when rate under RATE_LIMIT

# Miscellaneous
DEFAULT_FREQUENCY = 30  # a message every 30 seconds
GSE_EMIT_WHEN_STOPPED = False


########################################
# Redis
#
# Broadcaster Queues
INTERNAL_QUEUES = {"raw": "raw", "wire": "wire"}

LIVETRAFFIC_QUEUE = "lt"  # should be lt
LIVETRAFFIC_FORMATTER = "rttfc"  # {aitfc|rttfc|xpplanes}
LIVETRAFFIC_VERBOSE = True

# Redis Publish/Subscribe
PUBSUB_CHANNEL_PREFIX = "emitpy:"
QUEUE_DATA = key_path(REDIS_DATABASE.QUEUES.value, "data")


########################################
# geojson.io coloring for point and linestring features
# should be moved to parameters for custom coloring?
# leave it here for now to avoid bad taste coloring.
#
class FLIGHT_COLOR(Enum):
    OFFBLOCK = "#990000"
    PUSHBACK = "#FF0000"
    TAXI = "#FF3300"
    TAXIHOLD = "#CC3300"
    TAKE_OFF_HOLD = "#FF66D0"
    TAKE_OFF = "#0033CC"
    TAKE_OFF_ROLL = "#FF9900"
    ROTATE = "#FFCC00"
    LIFT_OFF = "#FFFF00"
    INITIAL_CLIMB = "#FFFF00"
    CLIMB = "#CCFF00"
    ACCELERATE = "#00FFFF"
    CRUISE = "#00FFFF"
    DECELERATE = "#00FFFF"
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
    TAKE_OFF_HOLD = "#FF66D0"
    TAKE_OFF = "#0033CC"
    TAKE_OFF_ROLL = "#0033CC"
    ROTATE = "#FFCC00"
    LIFT_OFF = "#FFFF00"
    INITIAL_CLIMB = "#FFFF00"
    CLIMB = "#CCFF00"
    CRUISE = "#00FFFF"
    ACCELERATE = "#00FFFF"
    DECELERATE = "#00FFFF"
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


class MISSION_COLOR(Enum):
    START = "#00dd00"
    CHECKPOINT = "#0000dd"
    EN_ROUTE = "#eeeeee"
    END = "#dd0000"


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


class SERVICE_PHASE_COLOR(Enum):
    START = "#008800"
    ARRIVED = "#00dd00"
    SERVICE_START = "#0000dd"
    SERVICE_END = "#000088"
    LEAVE = "#dd0000"
    END = "#880000"


class MESSAGE_COLOR(Enum):
    DEFAULT = "#888888"
