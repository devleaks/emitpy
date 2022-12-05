# Airspace Utility Classes
# With the exception of the restriction-related classes, all utility classes are GeoJSON features.
# The Airspace class is a network of air routes. It is an abstract class for building application-usable airspaces
# used for aircraft movements.
#
import logging
import math
import json
from abc import ABC, abstractmethod
from enum import Enum

from geojson import Point, LineString, Polygon, Feature
from turfpy.measurement import distance, destination

from emitpy.graph import Vertex, Edge, Graph
from emitpy.geo import FeatureWithProps
from emitpy.utils import key_path

logger = logging.getLogger("Airspace")


class CPIDENT(Enum):
    REGION = "region"
    AIRPORT = "airport"
    IDENT = "ident"
    POINTTYPE = "pointtype"

class SPEED_RESTRICTION(Enum):
    NONE  = "none"
    AT    = "at"
    ABOVE = "above"
    BELOW = "below"

class ALT_RESTRICTION(Enum):
    NONE  = "none"
    AT    = "at"
    ABOVE = "above"
    BELOW = "below"
    BETWEEN = "between"
    ILS_AT = "ils_at"

################################
#
# RESTRICTIONS
#
#
class Restriction:
    """
    A Restriction is an altitude and/or speed restriction for a section of an airspace.
    If a altitude restriction is set, an aircraft must fly above alt_min and/or below alt_max.
    If a speed restriction is set, the aircraft must fly fater than speed_min and/or slower than speed_max.
    If there is no restriction, use None for restriction.
    Consider this as a mixin.
    """
    def __init__(self, altmin: int = None, altmax: int = None, speedmin: float = None, speedmax: float = None):
        # Altitude constrains
        self.altmin = altmin        # In ft
        self.altmax = altmax
        self.altmin_type = None     # MSL, AGL, UL
        self.altmax_type = None
        # Speed constrains
        self.speedmin = speedmin    # In kn
        self.speedmax = speedmax
        # Bank angle constrains
        self.angle = None           # Bank angle in °.

    def getInfo(self):
        return {
            "type": type(self).__name__,
            "altmin": self.altmin,
            "altmax": self.altmax,
            "speedmin": self.speedmin,
            "speedmax": self.speedmax
        }

    def __str__(self):
        # @todo: make sure speed in ft.
        a = ""
        if self.altmin is not None:
            a = a + f"A {self.altmin} "
        if self.altmax is not None:
            a = a + f"B {self.altmax} "

        # @todo: make sure speed in kn.
        a = a + "/ "
        if self.speedmin is not None:
            a = a + f"A {self.speedmin} "
        if self.speedmax is not None:
            a = a + f"B {self.speedmax} "

        # @todo: may also have bank angle constrains
        # a = a + "/ "
        # if self.angle is not None:
        #     a = a + f"{self.angle}°"
        return a.strip()


    def setAltitudeRestriction(self, altmin: float, altmax: float):
        self.altmin = altmin
        self.altmax = altmax

    def getAltitudeRestriction(self):
        return (self.altmin, self.altmax)

    def checkAltitude(self, point: Point):
        if len(point.coordinates) < 3:  # no alt, must be ok ;-)
            return True
        alt = point.coordinates[2]
        retok = True
        if self.altmin is not None:
            retok = alt > self.altmin
        if self.altmax is not None:
            retok = retok and alt < self.altmax
        return retok

    def setSpeedRestriction(self, speedmin: float, speedmax: float):
        """
        If there is no restriction, set speed to None.
        """
        self.speedmin = speedmin
        self.speedmax = speedmax

    def getSpeedRestriction(self):
        return (self.speedmin, self.speedmax)

    def checkSpeed(self, feature: Feature, propname: str = "speed"):
        """
        Note: We assume same units for feature speed and constrains.
        We also assume feature has properties dict set.
        """
        retok = True
        if propname in feature.properties:
            speed = feature["properties"][propname]
            if self.speedmin is not None:
                retok = speed > self.speedmin
            if self.speedmax is not None:
                retok = retok and speed < self.speedmax
        return retok

    def hasAltitudeRestriction(self):
        return self.altmin is not None or self.altmax is not None

    def hasSpeedRestriction(self):
        return self.speedmin is not None or self.speedmax is not None

    def combine(self, restriction: "Restriction"):
        def nvl(a, b):
            return a if a is not None else b

        self.altmin = min(nvl(self.altmin, math.inf), nvl(restriction.altmin, math.inf))
        self.altmax = max(nvl(self.altmax, 0), nvl(restriction.altmax, 0))

        self.speedmin = max(nvl(self.speedmin, 0), nvl(restriction.speedmin, 0))
        self.speedmax = min(nvl(self.speedmax, math.inf), nvl(restriction.speedmax, math.inf))


class ControlledAirspace(FeatureWithProps):
    """
    This class describes a restricted airspace.
    @todo: we'll deal with the airspace restricted volumes later.
    @see: Little Navmap for "inspiration".
    """
    def __init__(self, name, region, airspace_class, restriction, area):
        FeatureWithProps.__init__(self, geometry=area, properties={})

        self.airspace_class = airspace_class
        self.restriction = restriction
        self.restrictions = [restriction]

    def add_restricton(self, restriction):
        self.restrictions.append(restriction)
        self.restriction.combine(restriction)


################################
#
# CONTROLLED POINTS (ABSTRACT CLASSES)
#
#
class SignificantPoint(Vertex):

    identsep = ":"

    """
    A SignificantPoint is a named point in a controlled airspace region.
    """
    def __init__(self, ident: str, region: str, airport: str, pointtype: str, lat: float, lon: float):
        name = SignificantPoint.mkId(region, airport, ident, pointtype)
        Vertex.__init__(self, node=name, point=Point((lon, lat)))
        self.ident = ident
        self.region = region
        self.airport = airport

    @staticmethod
    def mkId(region: str, airport: str, ident: str, pointtype: str = None) -> str:
        """
        Builds a SignificantPoint identifier from its region, airport (or enroute),
        identifier and point type (Fix, navaid, etc.)

        :param      region:     The region
        :type       region:     str
        :param      airport:    The airport
        :type       airport:    str
        :param      ident:      The identifier
        :type       ident:      str
        :param      pointtype:  The pointtype
        :type       pointtype:  str

        :returns:   { description_of_the_return_value }
        :rtype:     str
        """
        return region + SignificantPoint.identsep + ident + SignificantPoint.identsep + ("" if pointtype is None else pointtype) + SignificantPoint.identsep + airport

    @staticmethod
    def parseId(ident: str):
        """
        Reconstruct an identifier built by mkId function into its constituting parts.

        :param      ident:  The identifier
        :type       ident:  str
        """
        arr = ident.split(SignificantPoint.identsep)
        return {
            CPIDENT.REGION: arr[0],
            CPIDENT.IDENT: arr[1],
            CPIDENT.POINTTYPE: arr[2],
            CPIDENT.AIRPORT: arr[3]
        } if len(arr) == 4 else None

    def getInfo(self):
        """
        Gets a SignificantPoint information dictionary.
        """
        return {
            "class": type(self).__name__,
            "name": self.name,          # from Vertex()
            "ident": self.ident,
            "region": self.region,
            "airport": self.airport
        }

    def getFeature(self):
        """
        Get a simple, clean GeoJSON feature from the SignificantPoint
        """
        try:
            s = json.dumps(self)
            # if succeeded:
            return self
        except:
            # else, tries a simpler version
            return FeatureWithProps.new(self)


class RestrictedSignificantPoint(SignificantPoint, Restriction):
    """
    A SignificantPoint with a Restriction attached to it.
    """
    def __init__(self, ident: str, region: str, airport: str, pointtype: str, lat: float, lon: float):
        SignificantPoint.__init__(self, ident=ident, region=region, airport=airport, pointtype=pointtype, lat=lat, lon=lon)
        Restriction.__init__(self)


################################
#
# N A V A I D S
#
#
class NavAid(SignificantPoint):
    """
    Base class for all navigational aids.
    """
    # 46.646819444 -123.722388889  AAYRR KSEA K1 4530263
    def __init__(self, ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, name):
        # for marker beacons, we use their "name"/type (OM/MM/IM) rather than a generic MB (marker beacon)
        SignificantPoint.__init__(self, ident, region, airport, type(self).__name__ if type(self).__name__ != "MB" else name, lat, lon)
        self.elev = elev
        self.freq = freq
        self.ndb_class = ndb_class
        self.ndb_ident = ndb_ident
        self.name = name


class NDB(NavAid):  # 2
    """
    Non Directional Beacon
    """
    def __init__(self, ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, name):
        NavAid.__init__(self, ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, name)


class VOR(NavAid):  # 3
    """
    VHF Omnidirectional Range
    """
    def __init__(self, ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, name):
        NavAid.__init__(self, ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, name)


class LOC(NavAid):  # 4,5
    """
    Localiser
    """
    def __init__(self, ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, runway, name):
        NavAid.__init__(self, ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, name)
        self.runway = runway


class GS(NavAid):  # 6
    """
    GLide slope component of an ILS
    """
    def __init__(self, ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, runway, name):
        NavAid.__init__(self, ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, name)
        self.runway = runway


class MB(NavAid):  # 7,8,9
    """
    Marker Beacon, outer, middle or inner.
    """
    def __init__(self, ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, runway, name):
        NavAid.__init__(self, ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, name)
        self.runway = runway


class DME(NavAid):  # 12,13
    """
    Distance Measuring Equipment
    """
    def __init__(self, ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, name):
        NavAid.__init__(self, ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, name)


class FPAP(NavAid):  # 14
    """
    Final approach path alignment point (SBAS and GBAS)
    """
    def __init__(self, ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, runway, name):
        NavAid.__init__(self, ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, name)
        self.runway = runway


class GLS(NavAid):  # 16
    """
    GBAS Landing System
    """
    def __init__(self, ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, runway, name):
        NavAid.__init__(self, ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, name)
        self.runway = runway


class LTPFTP(NavAid):  # 16
    """
    Landing threshold point or fictitious threshold point of an SBAS/GBAS approach
    """
    def __init__(self, ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, runway, name):
        NavAid.__init__(self, ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, name)
        self.runway = runway


################################
#
# F I X E S
#
#
class Fix(SignificantPoint):
    """
    Non navigational aid fix.
    (we currently do not store how the fix is located, relative to surrounding navaids.)
    """
    # 46.646819444 -123.722388889  AAYRR KSEA K1 4530263
    def __init__(self, ident, region, airport, lat, lon, waypoint_type: str):
        SignificantPoint.__init__(self, ident, region, airport, type(self).__name__, lat, lon)
        self.waypoint_type = waypoint_type


################################
#
# A I R P O R T S
#
#
class Terminal(SignificantPoint):
    """
    This Terminaml is a SignificantPoint airport.
    """
    AS_WAYPOINTS = {}

    def __init__(self, name: str, lat: float, lon: float, alt: int, iata: str, longname: str, country: str, city: str):
        SignificantPoint.__init__(self, ident=name, region=name[0:2], airport=name, pointtype=type(self).__name__, lat=lat, lon=lon)
        self.iata = iata
        self.icao = name
        self.country = country
        self.city = city
        # logger.debug(f"Terminal:__init__: name: {self.id} / {name[0:2]}:{iata} / {longname}")
        self.longname = longname
        self._as_waypoint = f"{name[0:2]}:{iata}"
        Terminal.AS_WAYPOINTS[self.as_waypoint] = self  # keep region:iata name for reference in lnav

        if len(self["geometry"]["coordinates"]) > 2:
            self["geometry"]["coordinates"][2] = alt
        else:
            self["geometry"]["coordinates"].append(alt)

    @staticmethod
    def as_waypoint(name):
        return Terminal.AS_WAYPOINTS[name] if name in Terminal.AS_WAYPOINTS.keys() else None

    def getKey(self):
        return key_path(self.icao[0:2], self.icao[2:4])

    def getInfo(self):
        i = super().getInfo()
        i.update({
            "iata": self.iata,
            "icao": self.icao,
            "country": self.country,
            "city": self.city,
            "longname": self.longname
        })
        return i



################################
#
# W A Y P O I N T S
#
# AND OTHER SPECIAL POINTS
#
class Waypoint(SignificantPoint):  # same as fix
    """
    A Waypoint is a fix materialised by a VHF beacon of type navtype.
    """
    def __init__(self, ident: str, region: str, airport: str, lat: float, lon: float, navtype: str):
        # we may be should use navtype instead of "Waypoint" as point type
        SignificantPoint.__init__(self, ident, region, airport, type(self).__name__, lat, lon)
        self.navtype = navtype


class Hold(Restriction):
    """
    A Holding position.
        The course if the course (magnetic) of the inbound leg.
        Turn is Left or Right.
        Leg time is the duration of the leg or 0 for DME leg.
        Leg length is the length of the leg for DME leg or 0 for timed leg.
        Speed is the holding speed.
    """
    def __init__(self, fix: SignificantPoint, altmin: float, altmax: float, course: float, turn: str, leg_time: float, leg_length: float, speed: float):
        Restriction.__init__(self)
        self.fix = fix
        self.course = course
        self.turn = turn
        self.leg_time = leg_time  # min
        self.leg_length = leg_length  # unit?
        self.setAltitudeRestriction(altmin, altmax)
        self.setSpeedRestriction(speed, speed)


    def getInfo(self):
        return {
            "class": type(self).__name__,
            "restriction": super().getInfo(),
            "fix": self.fix.getInfo(),
            "course": self.course,
            "leg_time": self.leg_time,
            "leg_length": self.leg_length
        }

    def getRoute(self, speed: float, finesse: int = 6):
        """
        Make path from Hold data and aircraft speed.
        Returns an array of Feature<Point>

        :param      speed:  The speed
        :type       speed:  float
        """
        def line_arc(center, radius, start, end, steps=8):
            arc = []
            if end < start:
                end = end + 360
            step = (end - start) / steps
            a = start
            while a < end:
                p = destination(center, radius, a + 180)
                arc.append(p)
                a = a + step
            return arc

        # leg length
        length = speed * self.leg_time * 60 if self.leg_time > 0 else self.leg_length
        length = length / 1000  # km
        # circle radius:
        radius = length / math.pi
        # step = 180 / finesse

        # logger.debug(":Hold:getRoute: spd=%f len=%f rad=%f turn=%s legt=%f legl=%f" % (speed, length, radius, self.turn, self.leg_time, self.leg_length))

        # 4 corners and 2 arc centers p1 -> p2 -> p3 -> p4 -> p1
        p1 = self.fix
        p2 = destination(p1, length, self.course, {"units": "km"})

        hold = [p1, p2]  # start from p1, to to p2, then 180 turn:

        perpendicular = self.course + 90 * (1 if self.turn == "R" else -1)
        c23 = destination(p2, radius, perpendicular, {"units": "km"})

        logger.debug(f":Hold:getRoute: fix:{self.fix.id} turn={self.turn} course={self.course:f} perp={perpendicular:f}")

        start_angle = perpendicular
        if self.turn == "L":
            start_angle = start_angle - 180

        arc = line_arc(c23, radius, start_angle, start_angle + 180, finesse)
        if self.turn == "L":
            arc.reverse()
        hold = hold + arc

        p3 = destination(p2, 2*radius, perpendicular, {"units": "km"})
        hold.append(p3)
        p4 = destination(p1, 2*radius, perpendicular, {"units": "km"})
        hold.append(p4)

        c41 = destination(p1, radius, perpendicular, {"units": "km"})
        arc = line_arc(c41, radius, start_angle + 180, start_angle + 360, finesse)
        if self.turn == "L":
            arc.reverse()
        hold = hold + arc

        return hold


##########################
#
# S E G M E N T S
#
# AND COLLECION OF SEGMENTS
#
#
class AirwaySegment(Edge):
    """
    An AirwaySegment is a pair of SignificantPoints, directed, with optional altitude information.
    """
    def __init__(self, names: str, start: SignificantPoint, end: SignificantPoint, direction: bool, lowhigh: int, fl_floor: int, fl_ceil: int):
        dist = distance(start, end)
        Edge.__init__(self, src=start, dst=end, directed=direction, weight=dist)
        self.names = names.split("-")
        self.lowhigh = lowhigh
        self.fl_floor = fl_floor
        self.fl_ceil = fl_ceil

    def getKey(self):
        return key_path(self.start.id.replace(":", "-"), self.end.id.replace(":", "-"))

    def getInfo(self):
        return {
            "type": type(self).__name__,
            "start": self.start.id,
            "end": self.end.id,
            "names": self.names,
            "lowhigh": self.lowhigh,
            "fl_floor": self.fl_floor,
            "fl_ceil": self.fl_ceil,
            "length": self.weight,
            "directed": self.directed
        }


class Airway(FeatureWithProps):
    """
    An Airway is a named array of AirwaySegments.
    It is exposed as a LineString.
    """
    def __init__(self, name: str, route: [AirwaySegment]):
        self.name = name
        self.route = route
        arr = []
        var = ""
        for s in self.route:
            if first is None:
                first = s
                arr.append(s.start)
            arr.append(s.end)
            via = via + "," + s.names.join("-")
        FeatureWithProps.__init__(self, geometry=LineString(arr), properties={
            "name": name,
            "via": via
        })


##########################
#
# A I R   S P A C E
#
#
class AirspaceBase(Graph, ABC):
    """
    Airspace is a network of air routes.
    Vertices are airports, navaids, and fixes. Edges are airway segments.
    """

    def __init__(self, bbox=None, load_airways: bool = False):
        Graph.__init__(self)
        self.bbox = bbox
        self.load_airways = load_airways

        self.redis = None

        self.loaded = False
        self.airways_loaded = False

        self.airac_cycle = None

        self.all_points = {}
        self.holds = {}
        self.airspaces = {}


    def load(self, redis = None):
        if redis is not None and not self.load_airways:
            self.redis = redis
            return [True, "Airspace::load: Redis ready"]

        status = self.loadAirports()
        if not status[0]:
            return status

        status = self.loadNavaids()
        if not status[0]:
            return status

        status = self.loadFixes()
        if not status[0]:
            return status

        if self.load_airways:
            status = self.loadAirwaySegments()
            if not status[0]:
                return status

        status = self.loadAirspaces()
        if not status[0]:
            return status

        status = self.loadHolds()
        if not status[0]:
            return status

        return [True, f"Airspace loaded ({type(self).__name__})"]

    @abstractmethod
    def loadAirports(self):
        """
        Loads airports.
        """
        return [False, "no load implemented"]


    @abstractmethod
    def loadFixes(self):
        """
        Loads fixes.
        """
        return [False, "no load implemented"]


    @abstractmethod
    def loadNavaids(self):
        """
        Loads navaids.
        """
        return [False, "no load implemented"]


    @abstractmethod
    def loadAirwaySegments(self):
        """
        Loads airway segments.
        """
        return [False, "no load implemented"]


    @abstractmethod
    def loadAirspaces(self):
        """
        Loads airspaces and their restrictions.
        """
        return [False, "no load implemented"]


    @abstractmethod
    def loadHolds(self):
        """
        Loads holding points, their characteristics, and their restrictions.
        """
        return [False, "no load implemented"]


    def findHolds(self, name):
        """
        Finds holding positions with supplied name.

        :param      name:  The name
        :type       name:  { type_description }

        :returns:   { description_of_the_return_value }
        :rtype:     { return_type_description }
        """
        validholds = list(filter(lambda x: x.fix.id == name, self.holds.values()))
        return validholds
