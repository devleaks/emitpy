# Airspace Utility Classes
#
import logging

from geojson import Point, Feature
from turfpy.measurement import distance

from ..graph import Vertex, Edge, Graph

logger = logging.getLogger("Airspace")


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


################################
#
# CONTROLLED POINTS (ABSTRACT CLASSES)
#
#
class ControlledPoint(Vertex):
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
    def mkId(region: str, airport: str, ident: str, pointtype = None) -> str:
        return region + ":" + ident + ":" + ("" if pointtype is None else pointtype) + ":" + airport



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
    def __init__(self, name: str, lat: float, lon: float, iata: str, longname: str, country: str, city: str):
        ControlledPoint.__init__(self, name, name[0:2], name, type(self).__name__, lat, lon)
        self.iata = iata
        self.country = country
        self.city = city
        self.name = longname


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


class Hold(RestrictedControlledPoint):
    """
    A Holding position.
        The course if the course (magnetic) of the inbound leg.
        Turn is Left or Right.
        Leg time is the duration of the leg or 0 for DME leg.
        Leg length is the length of the leg for DME leg or 0 for timed leg.
        Speed is the holding speed.
    """
    def __init__(self, ident: str, region: str, airport: str, lat: float, lon: float, navtype: str, altmin: float, altmax: float,
                 course: float, turn: str, leg_time: float, leg_length: float, speed: float):
        RestrictedControlledPoint.__init__(self, ident=ident, region=region, airport=airport, pointtype=navtype, lat=lat, lon=lon)
        self.setAltitudeRestriction(altmin, altmax)
        self.setSpeedRestriction(speed, speed)
        self.course = course
        self.turn = turn
        self.leg_time = leg_time
        self.leg_length = leg_length


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
        self.loaded = False
        self.simairspacetype = "Generic"


    def load(self):
        """
        Chains loadAirports, loadFixes, loadNavaids, and loadAirwaySegments
        """
        return [False, "no load implemented"]


    def loadAirports(self):
        return [False, "no load implemented"]


    def loadFixes(self):
        return [False, "no load implemented"]


    def loadNavaids(self):
        return [False, "no load implemented"]


    def loadAirwaySegments(self):
        return [False, "no load implemented"]
