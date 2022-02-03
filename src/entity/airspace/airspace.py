# Airspace Utility Classes
#
import logging
import math
from enum import Enum

from geojson import Point, Feature
from turfpy.measurement import distance, destination

from ..graph import Vertex, Edge, Graph
from ..parameters import LOAD_AIRWAYS

logger = logging.getLogger("Airspace")

class CPIDENT(Enum):
    REGION = "region"
    AIRPORT = "airport"
    IDENT = "ident"
    POINTTYPE = "pointtype"


class Restriction:
    """
    A Restriction is an altitude and/or speed restriction.
    If a altitude restriction is set, an aircraft must fly above alt_min and/or below alt_max.
    If a speed restriction is set, the aircraft must fly fater than speed_min and/or slower than speed_max.
    If there is no restriction, use None for restriction.
    Consider this as a mixin.
    """
    def __init__(self):
        self.altmin = None
        self.altmax = None
        self.speedmin = None
        self.speedmax = None

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

################################
#
# CONTROLLED POINTS (ABSTRACT CLASSES)
#
#
class ControlledPoint(Vertex):

    identsep = ":"

    """
    A ControlledPoint is a named point in a controlled airspace region.
    """
    def __init__(self, ident: str, region: str, airport: str, pointtype: str, lat: float, lon: float):
        name = ControlledPoint.mkId(region, airport, ident, pointtype)
        Vertex.__init__(self, node=name, point=Point((lon, lat)))
        self.ident = ident
        self.region = region
        self.airport = airport

    @staticmethod
    def mkId(region: str, airport: str, ident: str, pointtype: str = None) -> str:
        return region + ControlledPoint.identsep + ident + ControlledPoint.identsep + ("" if pointtype is None else pointtype) + ControlledPoint.identsep + airport

    @staticmethod
    def parseId(ident: str):
        arr = ident.split(ControlledPoint.identsep)
        return {
            CPIDENT.REGION: arr[0],
            CPIDENT.IDENT: arr[1],
            CPIDENT.POINTTYPE: arr[2],
            CPIDENT.AIRPORT: arr[3]
        } if len(arr) == 4 else None


class RestrictedControlledPoint(ControlledPoint, Restriction):
    """
    """
    def __init__(self, ident: str, region: str, airport: str, pointtype: str, lat: float, lon: float):
        ControlledPoint.__init__(self, ident=ident, region=region, airport=airport, pointtype=pointtype, lat=lat, lon=lon)
        Restriction.__init__(self)



################################
#
# N A V A I D S
#
#
class NavAid(ControlledPoint):
    # 46.646819444 -123.722388889  AAYRR KSEA K1 4530263
    def __init__(self, ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, name):
        # for marker beacons, we use their "name"/type (OM/MM/IM) rather than a generic MB (marker beacon)
        ControlledPoint.__init__(self, ident, region, airport, type(self).__name__ if type(self).__name__ != "MB" else name, lat, lon)
        self.elev = elev
        self.freq = freq
        self.ndb_class = ndb_class
        self.ndb_ident = ndb_ident
        self.name = name


class NDB(ControlledPoint):  # 2

    def __init__(self, ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, name):
        NavAid.__init__(self, ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, name)


class VOR(ControlledPoint):  # 3

    def __init__(self, ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, name):
        NavAid.__init__(self, ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, name)


class LOC(ControlledPoint):  # 4,5

    def __init__(self, ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, runway, name):
        NavAid.__init__(self, ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, name)
        self.runway = runway


class GS(ControlledPoint):  # 6

    def __init__(self, ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, runway, name):
        NavAid.__init__(self, ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, name)
        self.runway = runway


class MB(ControlledPoint):  # 7,8,9

    def __init__(self, ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, runway, name):
        NavAid.__init__(self, ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, name)
        self.runway = runway


class DME(ControlledPoint):  # 12,13

    def __init__(self, ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, name):
        NavAid.__init__(self, ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, name)


class FPAP(ControlledPoint):  # 14

    def __init__(self, ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, runway, name):
        NavAid.__init__(self, ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, name)
        self.runway = runway


class GLS(ControlledPoint):  # 16

    def __init__(self, ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, runway, name):
        NavAid.__init__(self, ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, name)
        self.runway = runway


class LTPFTP(ControlledPoint):  # 16

    def __init__(self, ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, runway, name):
        NavAid.__init__(self, ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, name)
        self.runway = runway


################################
#
# F I X E S
#
#
class Fix(ControlledPoint):
    # 46.646819444 -123.722388889  AAYRR KSEA K1 4530263
    def __init__(self, ident, region, airport, lat, lon, waypoint_type: str):
        ControlledPoint.__init__(self, ident, region, airport, type(self).__name__, lat, lon)
        self.waypoint_type = waypoint_type


################################
#
# A I R P O R T S
#
#
class Apt(ControlledPoint):
    """
    This airport is a ControlledPoint airport.
    """
    def __init__(self, name: str, lat: float, lon: float, alt: int, iata: str, longname: str, country: str, city: str):
        ControlledPoint.__init__(self, ident=name, region=name[0:2], airport=name, pointtype=type(self).__name__, lat=lat, lon=lon)
        self.iata = iata
        self.country = country
        self.city = city
        self.name = longname
        if len(self["geometry"]["coordinates"]) > 2:
            self["geometry"]["coordinates"][2] = alt
        else:
            self["geometry"]["coordinates"].append(alt)


################################
#
# W A Y P O I N T S
#
# AND OTHER SPECIAL POINTS
#
class Waypoint(ControlledPoint):  # same as fix
    """
    A Waypoint is a fix materialised by a VHF beacon of type navtype.
    """
    def __init__(self, ident: str, region: str, airport: str, lat: float, lon: float, navtype: str):
        # we may be should use navtype instead of "Waypoint" as point type
        ControlledPoint.__init__(self, ident, region, airport, type(self).__name__, lat, lon)
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
    def __init__(self, fix: ControlledPoint, altmin: float, altmax: float, course: float, turn: str, leg_time: float, leg_length: float, speed: float):
        Restriction.__init__(self)
        self.fix = fix
        self.course = course
        self.turn = turn
        self.leg_time = leg_time
        self.leg_length = leg_length
        self.setAltitudeRestriction(altmin, altmax)
        self.setSpeedRestriction(speed, speed)


    def mkHold(self, speed: float, finesse: int = 8):
        """
        Make path from Hold data and aircraft speed.
        Returns an array of Feature<Point>

        :param      speed:  The speed
        :type       speed:  float
        """
        length = (speed/60) * self.leg_time if self.leg_time > 0 else self.leg_length
        # circle radius:
        radius = length / math.pi
        step = 180 / finesse

        # 4 corners and 2 arc centers p1 -> p2 -> p3 -> p4 -> p1
        p1 = self.fix
        p2 = destination(p1, length, self.course)

        arc = [p1, p2]

        perpendicular = self.course + 90 * (1 if self.turn == "L" else -1)
        c23 = destination(p2, length/2, perpendicular)
        curr = perpendicular - 180
        for i in range(0, finesse - 1):
            curr = curr + step
            p = destination(c23, radius, curr)
            arc.append(p)

        p3 = destination(p2, length, perpendicular)
        p4 = destination(p1, length, perpendicular)
        arc.append(p3)
        arc.append(p4)

        c41 = destination(p1, length/2, perpendicular)
        curr = perpendicular
        for i in range(0, finesse - 1):
            curr = curr + step
            p = destination(c41, radius, curr)
            arc.append(p)

        return arc


##########################
#
# S E G M E N T S
#
# AND COLLECION OF SEGMENTS
#
#
class AirwaySegment(Edge):
    """
    An AirwaySegment is a pair of ControlledPoints, directed, with optional altitude information.
    """
    def __init__(self, names: str, start: ControlledPoint, end: ControlledPoint, direction: bool, lowhigh: int, fl_floor: int, fl_ceil: int):
        dist = distance(start, end)
        Edge.__init__(self, src=start, dst=end, directed=direction, weight=dist)
        self.names = names.split("-")
        self.lowhigh = lowhigh
        self.fl_floor = fl_floor
        self.fl_ceil = fl_ceil


class AirwayRoute:
    """
    An AirwayRroute is a named array of AirwaySegments.
    """
    def __init__(self, name: str, route: [AirwaySegment]):
        self.name = name
        self.route = route


##########################
#
# A I R   S P A C E
#
#
class Airspace(Graph):
    """
    Airspace is a network of air routes.
    Vertices are airports, navaids, and fixes. Edges are airway (segements).
    """

    def __init__(self, bbox=None):
        Graph.__init__(self)
        self.bbox = bbox
        self.all_points = {}
        self.holds = {}
        self.loaded = False
        self.simairspacetype = "Generic"


    def load(self):
        status = self.loadAirports()

        if not status[0]:
            return [False, status[1]]

        status = self.loadNavaids()
        if not status[0]:
            return [False, status[1]]

        status = self.loadFixes()
        if not status[0]:
            return [False, status[1]]

        if LOAD_AIRWAYS:
            status = self.loadAirwaySegments()
            if not status[0]:
                return [False, status[1]]

        status = self.loadHolds()
        if not status[0]:
            return [False, status[1]]

        return [True, "Airspace loaded (%s)" % self.simairspacetype]


    def loadAirports(self):
        return [False, "no load implemented"]


    def loadFixes(self):
        return [False, "no load implemented"]


    def loadNavaids(self):
        return [False, "no load implemented"]


    def loadAirwaySegments(self):
        return [False, "no load implemented"]


    def loadHolds(self):
        return [False, "no load implemented"]

