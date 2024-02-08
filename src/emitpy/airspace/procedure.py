"""
CIFP is a collection of standard instrument arrival and departure procedures for an airport.
It also contains runways, approches and final approaches.
A couple of helper classes help deal with CIFP file parsing.
"""
from abc import ABC, abstractmethod
import os
import logging
import random
import math
from enum import Enum

from emitpy.constants import ID_SEP

from emitpy.geo.turf import distance, bearing, destination, Point, Feature
from emitpy.geo import FeatureWithProps

from emitpy.utils import ConvertDMSToDD, FT, cifp_alt_in_ft, cifp_speed, toKn, toKmh2
from emitpy.parameters import XPLANE_DIR
from .aerospace import Aerospace, NamedPoint

DEFAULT_DATA_DIR = os.path.join(XPLANE_DIR, "Resources", "default data")
CUSTOM_DATA_DIR = os.path.join(XPLANE_DIR, "Custom Data")


logger = logging.getLogger("Procedure")


class PROC_DATA(Enum):
    SEQ_NR = 0
    RT_TYPE = 1
    PROCEDURE_IDENT = 2
    TRANS_IDENT = 3
    FIX_IDENT = 4
    ICAO_CODE = 5
    SEC_CODE = 6
    SUB_CODE = 7
    DESC_CODE = 8
    TURN_DIR = 9
    RNP = 10
    PATH_TERM = 11
    TDV = 12
    RECD_NAV = 13
    ICAO_CODE2 = 14
    SEC_CODE2 = 15
    SUB_CODE2 = 16
    ARC_RAD = 17
    THETA = 18
    RHO = 19
    OB_MAG_CRS = 20
    HOLD_DIST_TIME = 21
    ALT_DESC = 22  # ! Important
    _MIN_ALT1 = 23  # ! Important
    _MIN_ALT2 = 24  # ! Important
    TRANS_ALTITUDE_LEVEL = 25
    _SPEED_LIM_DESC = 26  # ! Important
    SPEED_LIMIT = 27  # ! Important
    VERT_ANGLE = 28
    _5_293 = 29
    CENTER_FIX_PROC_TURN = 30
    ICAO_CODE3 = 31
    SEC_CODE3 = 32
    SUB_CODE3 = 33
    MULTI_CD = 34
    GPS_FMS_IND = 35
    RT_TYPE2 = 36
    RT_TYPE3 = 37


class PROC_CONT_DATA(Enum):
    LS_AUTH = 0
    LSN = 1
    RT_TYPE = 2


class RWY_DATA(Enum):
    RUNWAY_ID = 0
    RWY_GRAD = 1
    Ellipsoidal_Height = 2
    LANDING_THRES_ELEV = 3
    TCHVI = 4
    LOC = 5
    MLS = 5
    GLS_IDENT = 5
    CAT = 6
    TCH = 7
    LATITUDE = 8
    LONGITUDE = 9
    DSPLCD_THR = 10


################################
#
# RESTRICTIONS & CLASSES WITH RESTRICTION(S)
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

    def __init__(self, altmin: int = None, altmax: int = None, speed: float = None):
        self._source = None
        # Altitude constrains
        self.alt1 = altmin  # In ft
        self.alt2 = altmax
        self.alt1_type = None  # MSL, AGL, UL
        self.alt2_type = None
        self.alt_restriction_type = None
        # Speed constrains
        self.speed = speed  # In kn
        self.speed_restriction_type = None
        # Bank angle constrains
        self.angle = None  # Bank angle in °.
        self.restrictions = []

    def getInfo(self):
        return {
            "type": type(self).__name__,
            "alt1": self.alt1,
            "alt2": self.alt2,
            "alt_desc": self.alt_restriction_type,
            "speed": self.speed,
            "speed_desc": self.speed_restriction_type,
        }

    def hasRestriction(self) -> bool:
        return self.hasAltitudeRestriction() or self.hasSpeedRestriction()

    def getRestrictionDesc(self, verbose: bool = False):
        if not self.hasAltitudeRestriction() and not self.hasSpeedRestriction() and verbose:
            return "no restriction"

        a = self.getAltitudeRestrictionDesc() + "/" + self.getSpeedRestrictionDesc()
        if self.angle is not None:
            a = a + f"/{self.angle}°"
        a = a.strip()
        return "" if a in ["/", "@/@"] else a

    def setAltitudeRestriction(self, altmin: float, altmax: float):
        self.alt1 = altmin
        self.alt2 = altmax

    def getAltitudeRestrictionDesc(self) -> str:
        a = ""
        if self.alt1 is not None:
            a = "?" if self.alt_restriction_type is None else self.alt_restriction_type
            if a == " ":
                a = "@"  # more explicit on display
            a = f"{a}{self.alt1}"
            if self.alt2 is not None:
                a = f"{a},{self.alt2}"
        elif self.alt2 is not None:
            a = "?" if self.alt_restriction_type is None else self.alt_restriction_type
            if a == " ":
                a = "@"  # more explicit on display
            a = f"{a}{self.alt2}"
        return a

    def hasAltitudeRestriction(self) -> bool:
        return self.alt1 is not None or self.alt2 is not None

    def checkAltitude(self, point: Point):
        if len(point.coordinates) < 3:  # no alt, must be ok ;-)
            return True
        alt = point.coordinates[2]
        retok = True
        if self.alt1 is not None:
            retok = alt > self.alt1
        if self.alt2 is not None:
            retok = retok and alt < self.alt2
        return retok

    def setSpeedRestriction(self, speed: float):
        """
        If there is no restriction, set speed to None.
        """
        self.speed = speed

    def getSpeedRestrictionDesc(self):
        a = ""
        if self.speed is not None:
            a = "?" if self.speed_restriction_type is None else self.speed_restriction_type
            if a == " ":
                a = "@"  # more explicit on display
            a = f"{a}{self.speed}"
        return a

    def hasSpeedRestriction(self) -> bool:
        return self.speed is not None

    def checkSpeed(self, feature: Feature, propname: str = "speed"):
        """
        Note: We assume same units for feature speed and constrains.
        We also assume feature has properties dict set.
        """
        speed = toKn(toKmh2(ms=feature["properties"].get(propname)))
        if speed is not None:
            if self.speed_restriction_type in [" ", "@"]:
                return (speed - self.speed) < 5
            elif self.speed_restriction_type == "-":
                return speed < self.speed
            elif self.speed_restriction_type == "+":
                return speed > self.speed
            else:
                logger.warning(f"invalid control speed type '{self.speed_restriction_type}'")
        return False

    def combine(self, restriction):
        def nvl(a, b):
            return a if a is not None else b

        self.restrictions.append(restriction)

        self.alt1 = min(nvl(self.alt1, math.inf), nvl(restriction.alt1, math.inf))
        if self.alt1 == math.inf:
            self.alt1 = None
        self.alt2 = max(nvl(self.alt2, 0), nvl(restriction.alt2, 0))
        if self.alt2 == 0:
            self.alt2 = None

        self.speed = max(nvl(self.speed, 0), nvl(restriction.speed, 0))
        if self.speed == 0:
            self.speed = None

        self.alt_restriction_type = nvl(self.alt_restriction_type, restriction.alt_restriction_type)
        self.speed_restriction_type = nvl(self.speed_restriction_type, restriction.speed_restriction_type)


class FeatureWithRestriction(FeatureWithProps):
    """
    A NamedPoint with a Restriction attached to it.
    """

    def __init__(self, geometry, properties={}, **extra):
        FeatureWithProps.__init__(self, geometry=geometry, properties=properties, extra=extra)
        self.restrictions = []
        self.restriction = None

    def add_restriction(self, restriction):
        self.restrictions.append(restriction)
        if self.restriction is None:
            self.restriction = restriction
        else:
            self.restriction.combine(restriction)

    def has_restriction(self):
        return self.restriction is not None


class NamedPointWithRestriction(NamedPoint, Restriction):
    """
    A NamedPoint with a Restriction attached to it.
    """

    def __init__(self, ident: str, region: str, airport: str, pointtype: str, lat: float, lon: float):
        NamedPoint.__init__(self, ident=ident, region=region, airport=airport, pointtype=pointtype, lat=lat, lon=lon)
        Restriction.__init__(self)


class ControlledAirspace(FeatureWithProps, Restriction):
    """
    This class describes a restricted airspace.
    @todo: we'll deal with the airspace restricted volumes later.
    @see: Little Navmap for "inspiration".
    """

    def __init__(self, name, region, airspace_class, area, altmin, altmax, altmin_type, altmax_type):
        FeatureWithProps.__init__(self, geometry=area, properties={})
        Restriction.__init__(self)

        self.airspace_class = airspace_class
        self.setAltitudeRestriction(altmin, altmax)
        self.alt1_type = altmin_type
        self.alt2_type = altmax_type

    def add_restricton(self, restriction):
        self.combine(restriction)


class Hold(Restriction):
    """
    A Holding position.
        The course if the course (magnetic) of the inbound leg.
        Turn is Left or Right.
        Leg time is the duration of the leg or 0 for DME leg.
        Leg length is the length of the leg for DME leg or 0 for timed leg.
        Speed is the holding speed.
    """

    def __init__(self, fix: NamedPoint, altmin: float, altmax: float, course: float, turn: str, leg_time: float, leg_length: float, speed: float):
        Restriction.__init__(self)
        self.fix = fix
        self.course = course
        self.turn = turn
        self.leg_time = leg_time  # min
        self.leg_length = leg_length  # unit?
        self.setAltitudeRestriction(altmin, altmax)
        self.setSpeedRestriction(speed)

    def getInfo(self):
        return {
            "class": type(self).__name__,
            "restriction": super().getInfo(),
            "fix": self.fix.getInfo(),
            "course": self.course,
            "leg_time": self.leg_time,
            "leg_length": self.leg_length,
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

        # logger.debug("spd=%f len=%f rad=%f turn=%s legt=%f legl=%f" % (speed, length, radius, self.turn, self.leg_time, self.leg_length))

        # 4 corners and 2 arc centers p1 -> p2 -> p3 -> p4 -> p1
        p1 = self.fix
        p2 = destination(p1, length, self.course)

        hold = [p1, p2]  # start from p1, to to p2, then 180 turn:

        perpendicular = self.course + 90 * (1 if self.turn == "R" else -1)
        c23 = destination(p2, radius, perpendicular)

        logger.debug(f"fix:{self.fix.id} turn={self.turn} course={self.course:f} perp={perpendicular:f}")

        start_angle = perpendicular
        if self.turn == "L":
            start_angle = start_angle - 180

        arc = line_arc(c23, radius, start_angle, start_angle + 180, finesse)
        if self.turn == "L":
            arc.reverse()
        hold = hold + arc

        p3 = destination(p2, 2 * radius, perpendicular)
        hold.append(p3)
        p4 = destination(p1, 2 * radius, perpendicular)
        hold.append(p4)

        c41 = destination(p1, radius, perpendicular)
        arc = line_arc(c41, radius, start_angle + 180, start_angle + 360, finesse)
        if self.turn == "L":
            arc.reverse()
        hold = hold + arc

        return hold


################################
#
# PROCEDURES
#
#
class ProcedureData:
    """
    Represent one line of more of procedure data from CIFP file.
    If the line of instruction has more lines of data, they get collected in this instance.
    """

    # CIFP line for this airport. Example line:
    # APPCH:030,A,I25RZ,KERKY,CF25R,EB,P,C,EE B,R,   ,CF,Y,IBR,EB,P,I,      ,0644,0130,2140,0085,+,02000,     ,     , ,   ,    ,   , , , , , ,0,D,S;
    # PROC :[params]                                   ↑
    #       params[PROC_DATA.PATH_TERM] = param[11]----+  (CF, Course to Fix)
    #
    def __init__(self, line):
        self.procedure = None
        self.data = []
        self.params = []
        a = line.split(":")
        if len(a) < 2:
            logger.debug("invalid line '%s'", line)
        else:
            self.procedure = a[0]
            self.params = a[1].split(",")
        if len(self.params) == 0:
            logger.debug("invalid line '%s', no params", line)

    def proc(self):
        """
        Returns the procedure type (SID, STAR, RWY, APPCH)
        """
        return self.procedure

    def name(self):
        """
        Returns the procedure name, if present
        """
        if self.proc() == "RWY":
            return self.params[0]
        return self.params[2]

    def addData(self, data):
        """
        Adds a line of procedure data

        :param      data:  The data
        :type       data:  { type_description }
        """
        return self.data.append(data)

    def seq(self):
        """
        Returns the procedure data line sequence number
        """
        if self.proc() in ("RWY", "PRDAT"):
            return 0
        return int(self.params[0])

    def line(self):
        """
        Returns the whole procedure line
        """
        return ",".join(self.params)

    def param(self, name: PROC_DATA):
        """
        Returns the requested procedure data or parameter.
        Name of parameter is coded in PROC_DATA enum.

        :param      name:  The name
        :type       name:  PROC_DATA
        """
        return self.params[name.value]

    def runway(self):
        """
        This function reports the runway to which the procedure applies.
        IT IS NOT NECESSARILY A REAL RUNWAY NAME.
        For exemple,
        - if a function relates to all runways, this procedure will return ALL
        - if a function relates to both NNL and NNR runways, this procedure will return NNB (both)
        This is taken into account when selecting procedures for a given runway.
        """
        if self.proc() == "RWY":
            return self.name
        if self.proc() == "APPCH":
            s = self.param(PROC_DATA.PROCEDURE_IDENT)
            l = -3 if s[-1] in list("LCR") else -2
            return "RW" + s[l:]
        return self.param(PROC_DATA.TRANS_IDENT)

    def getRestriction(self):
        """@todo"""
        altmin = cifp_alt_in_ft(self.param(PROC_DATA._MIN_ALT1))
        altmax = cifp_alt_in_ft(self.param(PROC_DATA._MIN_ALT2))
        speedlim = cifp_speed(self.param(PROC_DATA.SPEED_LIMIT))
        r = Restriction(altmin=altmin, altmax=altmax, speed=speedlim)
        r._source = self
        r.alt_restriction_type = self.param(PROC_DATA.ALT_DESC)
        r.speed_restriction_type = self.param(PROC_DATA._SPEED_LIM_DESC)
        return r


class Procedure(ABC):
    """
    A Procedure is a named array of ProcedureData (lines or routes)
    Abstract class.
    """

    def __init__(self, name: str):
        self.name = name
        self.runway = None
        self.route = {}  # list of CIFP lines

    def add(self, line: ProcedureData):
        """
        Adds a line of procedure data to the procedure

        :param      line:  The line
        :type       line:  ProcedureData
        """
        if len(self.route) == 0:  # First time, sets runway CIFP name
            self.runway = line.runway()
        self.route[line.seq()] = line

    def getNamedPointWithRestriction(self, airspace, vertex, restriction: Restriction):
        p = airspace.getNamedPoint(vertex)
        if p is not None:
            pointtype = p.id.split(ID_SEP)[-2]
            u = NamedPointWithRestriction(ident=p.ident, region=p.region, airport=p.airport, pointtype=pointtype, lat=p.lat(), lon=p.lon())
            u.combine(restriction)
            logger.debug(f"getNamedPointWithRestriction: {type(self).__name__} {self.name}: {vertex} ({u.getRestrictionDesc(True)})")
            return u
        logger.warning(f"getNamedPointWithRestriction: no vertex named {vertex}")
        return None

    @abstractmethod
    def getRoute(self, airspace: Aerospace):
        pass

    @abstractmethod
    def prepareRestrictions(self, route):
        pass


class SID(Procedure):
    """
    A Standard Instrument Departure is a special instance of a Procedure.
    """

    def __init__(self, name: str):
        Procedure.__init__(self, name)

    def getRoute(self, airspace: Aerospace):
        """
        Returns an array of vertices from the Aerospace
        that follow the SID

        :param      airspace:  The airspace
        :type       airspace:  Aerospace
        """
        a = []
        for v in self.route.values():
            fid = v.param(PROC_DATA.FIX_IDENT).strip()
            if len(fid) > 0:
                vid = v.param(PROC_DATA.ICAO_CODE) + ":" + v.param(PROC_DATA.FIX_IDENT) + ":"
                # logger.debug("SID:getRoute: %s" % vid)
                vtxs = list(filter(lambda x: x.startswith(vid), airspace.vert_dict.keys()))
                if len(vtxs) > 0 and len(vtxs) < 3:  # there often is both a VOR and a DME at same location, we keep either one
                    a.append(self.getNamedPointWithRestriction(airspace=airspace, vertex=vtxs[0], restriction=v.getRestriction()))
                elif len(vtxs) > 2:
                    logger.warning(f"SID:getRoute: vertex ambiguous {vid} ({len(vtxs)}, {vtxs})")
                else:
                    logger.warning("SID:getRoute: vertex not found %s", vid)

        self.prepareRestrictions(a)
        return a

    def prepareRestrictions(self, route):
        def apply_speed_restriction_before(r, idx):
            if idx == 0:
                return
            curr = r[idx]
            stop = False
            j = idx - 1
            # print(">>> SENTER", idx, curr.getProp("_restricted_speed"))
            while j >= 0 and not stop:
                prec = r[j]
                # print(">>>", j, prec.getProp("_restricted_speed"))
                if prec.hasSpeedRestriction():  # element has already a speed restriction
                    # print("prec has restriction", j, ">" + prec.getSpeedRestrictionDesc() + "<")
                    stop = True
                else:  # we copy/apply the restriction to preceeding wp
                    spd_desc = curr.speed_restriction_type
                    # print("curr type", spd_desc)
                    if spd_desc in [" ", "-"]:
                        # print("prec set", curr.getProp("_speed_max"))
                        prec.setProp("_speed_max", curr.getProp("_speed_max"))
                j = j - 1

        def apply_alt_restriction_before(r, idx):
            curr = r[idx]
            stop = False
            j = idx - 1
            # print(">>> AENTER", idx, curr.getProp("_restricted_altitude"))
            while j >= 0 and not stop:
                prec = r[j]
                # print(">>>", j, prec.getProp("_restricted_altitude"))
                if prec.hasAltitudeRestriction():  # element has already a speed restriction
                    # print("prec has restriction", j, ">" + prec.getAltitudeRestrictionDesc() + "<")
                    stop = True
                else:  # we copy/apply the restriction to preceeding wp
                    alt_desc = curr.alt_restriction_type
                    # print("curr type", alt_desc)
                    if alt_desc in [" ", "-"]:
                        # print("prec set max", curr.getProp("_alt_max"))
                        prec.setProp("_alt_max", curr.getProp("_alt_max"))
                    elif alt_desc in ["+"]:
                        # print("prec set min", curr.getProp("_alt_min"))
                        prec.setProp("_alt_max", curr.getProp("_alt_min"))
                j = j - 1

        # Speed
        for i in range(len(route)):
            v = route[i]
            if v.hasSpeedRestriction():
                # print(i, v.getId(), v.getSpeedRestrictionDesc())
                v.setProp("_restricted_speed", v.getSpeedRestrictionDesc())
                spd_desc = v.speed_restriction_type
                if spd_desc in [" ", "@"]:
                    v.setProp("_speed_min", v.speed)
                    v.setProp("_speed_max", v.speed)
                    v.setProp("_speed_target", v.speed)  # mandatory to pass wp at that speed
                elif spd_desc == "+":
                    v.setProp("_speed_min", v.speed)
                elif spd_desc == "-":
                    v.setProp("_speed_max", v.speed)
                apply_speed_restriction_before(route, i)
            # else:
            #     print(i, v.getId(), "no restriction")
        logger.debug("SID prepared for speed restrictions")

        # Altitude
        for i in range(len(route)):
            v = route[i]
            if v.hasAltitudeRestriction():
                # print(i, v.getId(), v.getAltitudeRestrictionDesc())
                v.setProp("_restricted_altitude", v.getAltitudeRestrictionDesc())
                alt_desc = v.alt_restriction_type
                if alt_desc in [" ", "@"]:
                    v.setProp("_alt_min", v.alt1)
                    v.setProp("_alt_max", v.alt1)
                    v.setProp("_alt_target", v.alt1)  # mandatory to pass wp at that alt
                elif alt_desc == "B":
                    if v.alt1 > v.alt2:
                        v.setProp("_alt_min", v.alt2)
                        v.setProp("_alt_max", v.alt1)
                    else:
                        v.setProp("_alt_min", v.alt1)
                        v.setProp("_alt_max", v.alt2)
                elif alt_desc in ["+"]:
                    v.setProp("_alt_min", v.alt1)
                    v.setProp("_alt_target", v.alt1)  # mandatory to pass wp at that alt
                elif alt_desc in ["C", "D"]:
                    v.setProp("_alt_min", v.alt2)
                elif alt_desc == "-":
                    v.setProp("_alt_max", v.alt1)
                apply_alt_restriction_before(route, i)
            # else:
            #     print(i, v.getId(), "no restriction")
        logger.debug("SID prepared for altitude restrictions")

        # Find last alt restriction
        j = len(route) - 1
        last_alt_restriction = None
        last_alt_restr_index = None
        while j >= 0 and last_alt_restriction is None:
            if route[j].hasAltitudeRestriction():
                last_alt_restriction = route[j]
                last_alt_restr_index = j
            j = j - 1
        if last_alt_restriction is None:
            logger.debug("SID has no alt restriction")
        else:
            pass


class STAR(Procedure):
    """
    A Standard Terminal Arrival Route is a special instance of a Procedure.
    """

    def __init__(self, name: str):
        Procedure.__init__(self, name)

    def getRoute(self, airspace: Aerospace):
        """
        Returns an array of vertices from the Aerospace
        that follow the STAR

        :param      airspace:  The airspace
        :type       airspace:  Aerospace
        """
        a = []
        for v in self.route.values():
            fid = v.param(PROC_DATA.FIX_IDENT).strip()
            if len(fid) > 0:
                vid = v.param(PROC_DATA.ICAO_CODE) + ":" + v.param(PROC_DATA.FIX_IDENT) + ":"
                # logger.debug("STAR:getRoute: %s" % vid)
                vtxs = list(filter(lambda x: x.startswith(vid), airspace.vert_dict.keys()))
                if len(vtxs) > 0 and len(vtxs) < 3:  # there often is both a VOR and a DME at same location
                    a.append(self.getNamedPointWithRestriction(airspace=airspace, vertex=vtxs[0], restriction=v.getRestriction()))
                elif len(vtxs) > 2:
                    logger.warning("STAR:getRoute: vertex ambiguous %s (%d, %s)" % (vid, len(vtxs), vtxs))
                else:
                    logger.warning("STAR:getRoute: vertex not found %s", vid)

        self.prepareRestrictions(a)
        return a

    def prepareRestrictions(self, route):
        # Speed
        curr_limit = None
        for i in range(len(route)):
            v = route[i]
            if v.hasSpeedRestriction():
                print(">>> has speed restriction", v.ident, v.getSpeedRestrictionDesc())
                v.setProp("_restricted_speed", v.getSpeedRestrictionDesc())
                spd_desc = v.speed_restriction_type
                if spd_desc in [" ", "@"]:
                    v.setProp("_speed_min", v.speed)
                    v.setProp("_speed_max", v.speed)
                    v.setProp("_speed_target", v.speed)
                elif spd_desc == "+":
                    v.setProp("_speed_min", v.speed)
                elif spd_desc == "-":
                    v.setProp("_speed_max", v.speed)
                curr_limit = v
            elif curr_limit is not None:  # carry restriction forward
                print(">>> carry forward speed restriction", v.ident, curr_limit.getSpeedRestrictionDesc())
                spd_desc = curr_limit.speed_restriction_type
                if spd_desc in [" ", "@"]:
                    v.setProp("_speed_min", curr_limit.getProp("_speed_min"))
                    v.setProp("_speed_max", curr_limit.getProp("_speed_max"))
                    v.setProp("_speed_target", curr_limit.getProp("_speed_target"))
                elif spd_desc == "+":
                    v.setProp("_speed_min", curr_limit.getProp("_speed_min"))
                elif spd_desc == "-":
                    v.setProp("_speed_max", curr_limit.getProp("_speed_max"))
        logger.debug("STAR prepared for speed restrictions")

        # Altitude
        curr_limit = None
        first = True
        for i in range(len(route)):
            v = route[i]
            if v.hasAltitudeRestriction():
                print(">>> has altitude restriction", v.ident, v.getAltitudeRestrictionDesc())
                v.setProp("_restricted_altitude", v.getAltitudeRestrictionDesc())
                alt_desc = v.alt_restriction_type
                if alt_desc in [" ", "@"]:
                    v.setProp("_alt_min", v.alt1)
                    v.setProp("_alt_max", v.alt1)
                    v.setProp("_alt_target", v.alt1)  # mandatory to pass wp at that alt
                elif alt_desc == "B":
                    if v.alt1 > v.alt2:
                        v.setProp("_alt_min", v.alt2)
                        v.setProp("_alt_max", v.alt1)
                    else:
                        v.setProp("_alt_min", v.alt1)
                        v.setProp("_alt_max", v.alt2)
                elif alt_desc in ["+"]:
                    v.setProp("_alt_min", v.alt1)
                elif alt_desc in ["C", "D"]:
                    v.setProp("_alt_min", v.alt2)
                elif alt_desc == "-":
                    v.setProp("_alt_max", v.alt1)
                    if first:
                        v.setProp("_alt_target", v.alt1)  # first "below" alt is target alt
                        first = False
                curr_limit = v
            # elif curr_limit is not None:
            #     print(">>> carry forward altitude restriction", v.ident, curr_limit.getAltitudeRestrictionDesc())
        logger.debug("STAR prepared for altitude restrictions")


class APPCH(Procedure):
    """
    Approach procedure to runway.

    APPCH:030,D,D16L, ,MD16L,OT,P,C,E  M, ,   ,CF, ,DOH,OT,D, ,      ,3460,0056,1660,0063, ,00995,     ,     , ,   ,-300,   , , , , , ,0, ,S;

    """

    def __init__(self, name: str):
        Procedure.__init__(self, name)

    def getRoute(self, airspace: Aerospace):
        """
        Returns an array of vertices from the Aerospace
        that follow the approach.

        :param      airspace:  The airspace
        :type       airspace:  Aerospace
        """
        interrupted = False
        a = []
        for v in self.route.values():
            code = v.param(PROC_DATA.DESC_CODE)[0]
            if code == "E" and not interrupted:
                vid = v.param(PROC_DATA.ICAO_CODE) + ":" + v.param(PROC_DATA.FIX_IDENT) + ":"
                # logger.debug("APPCH:getRoute: %s" % vid)
                vtxs = list(filter(lambda x: x.startswith(vid), airspace.vert_dict.keys()))
                if len(vtxs) > 0 and len(vtxs) < 3:  # there often is both a VOR and a DME at same location
                    a.append(self.getNamedPointWithRestriction(airspace=airspace, vertex=vtxs[0], restriction=v.getRestriction()))
                elif len(vtxs) > 2:
                    logger.warning("APPCH:getRoute: vertex ambiguous %s (%d, %s)" % (vid, len(vtxs), vtxs))
                else:
                    logger.warning("APPCH:getRoute: vertex not found %s", vid)
            else:
                if not interrupted:
                    logger.debug(
                        "APPCH:getRoute: interrupted %s", "" if len(v.param(PROC_DATA.FIX_IDENT).strip()) == 0 else (f" at {v.param(PROC_DATA.FIX_IDENT)} ")
                    )
                interrupted = True

        self.prepareRestrictions(a)
        return a

    def prepareRestrictions(self, route):
        # Speed
        curr_limit = None
        for i in range(len(route)):
            v = route[i]
            if v.hasSpeedRestriction():
                print(">>> has speed restriction", v.ident, v.getSpeedRestrictionDesc())
                v.setProp("_restricted_speed", v.getSpeedRestrictionDesc())
                spd_desc = v.speed_restriction_type
                if spd_desc in [" ", "@"]:
                    v.setProp("_speed_min", v.speed)
                    v.setProp("_speed_max", v.speed)
                    v.setProp("_speed_target", v.speed)
                elif spd_desc == "+":
                    v.setProp("_speed_min", v.speed)
                elif spd_desc == "-":
                    v.setProp("_speed_max", v.speed)
                curr_limit = v
            elif curr_limit is not None:  # carry restriction forward
                print(">>> carry forward speed restriction", v.ident, curr_limit.getSpeedRestrictionDesc())
                spd_desc = curr_limit.speed_restriction_type
                if spd_desc in [" ", "@"]:
                    v.setProp("_speed_min", curr_limit.getProp("_speed_min"))
                    v.setProp("_speed_max", curr_limit.getProp("_speed_max"))
                    v.setProp("_speed_target", curr_limit.getProp("_speed_target"))
                elif spd_desc == "+":
                    v.setProp("_speed_min", curr_limit.getProp("_speed_min"))
                elif spd_desc == "-":
                    v.setProp("_speed_max", curr_limit.getProp("_speed_max"))
        logger.debug("APPCH prepared for speed restrictions")

        # Altitude
        curr_limit = None
        first = True
        for i in range(len(route)):
            v = route[i]
            if v.hasAltitudeRestriction():
                print(">>> has altitude restriction", v.ident, v.getAltitudeRestrictionDesc())
                v.setProp("_restricted_altitude", v.getAltitudeRestrictionDesc())
                alt_desc = v.alt_restriction_type
                if alt_desc in [" ", "@"]:
                    v.setProp("_alt_min", v.alt1)
                    v.setProp("_alt_max", v.alt1)
                    v.setProp("_alt_target", v.alt1)  # mandatory to pass wp at that alt
                elif alt_desc == "B":
                    if v.alt1 > v.alt2:
                        v.setProp("_alt_min", v.alt2)
                        v.setProp("_alt_max", v.alt1)
                    else:
                        v.setProp("_alt_min", v.alt1)
                        v.setProp("_alt_max", v.alt2)
                elif alt_desc in ["+"]:
                    v.setProp("_alt_min", v.alt1)
                elif alt_desc in ["C", "D"]:
                    v.setProp("_alt_min", v.alt2)
                elif alt_desc == "-":
                    v.setProp("_alt_max", v.alt1)
                    if first:
                        v.setProp("_alt_target", v.alt1)  # first "below" alt is target alt
                        first = False
                curr_limit = v
            # elif curr_limit is not None:
            #     print(">>> carry forward altitude restriction", v.ident, curr_limit.getAltitudeRestrictionDesc())
        logger.debug("APPCH prepared for altitude restrictions")


class RWY(Procedure):
    """
    A runway for starting a SID or terminating a STAR.
    We distinguish the "aeronautical" Aerospace.Procedure.RWY (a threshold geolocalized Point)
    from the geographical/geometrical Geo.Runway (a geo-localized polygon)
    """

    def __init__(self, name: str, airport: str):
        Procedure.__init__(self, name)
        self.airport = airport  ## Needed to create valid control point for runway
        self.runway = name
        self.point = None
        self.end = None
        self.uuid = name  # not correct, but acceptable default value, set unique for both "sides" of runway
        # some rare runways are one way only... (EDDF)

    def add(self, line: ProcedureData):
        if self.point is not None:
            logger.warning("Cannot add to an already defined runway")
            return

        #     0     1     2      3     4 5    6 7             8          9
        # RWY:RW16L,     ,      ,00013, ,IDE ,3,   ;N25174597,E051363196,0000;
        self.route[0] = line
        if self.has_latlon():
            self.point = NamedPointWithRestriction(
                ident=line.params[0], region=self.airport[0:2], airport=self.airport, pointtype="RWY", lat=self.getLatitude(), lon=self.getLongitude()
            )
            self.setAltitude(float(self.route[0].params[3]) * FT)
        else:
            logger.warning(f"Runway {self.runway} has no threshold")

    def has_latlon(self):
        """
        Returns whether the RWY procedure has latitude and longitude of threshold point
        """
        return (self.route[0].params[7].split(";")[1] != "") and (self.route[0].params[8] != "")

    def getLatitude(self):
        """
        Returns latitude of threshold point
        """
        latstr = self.route[0].params[7].split(";")[1]
        return ConvertDMSToDD(latstr[1:3], latstr[3:5], int(latstr[5:9]) / 100, latstr[0])

    def getLongitude(self):
        """
        Returns longitude of threshold point
        """
        lonstr = self.route[0].params[8]
        return ConvertDMSToDD(lonstr[1:4], lonstr[4:6], int(lonstr[6:10]) / 100, lonstr[0])

    def setAltitude(self, alt):
        """
        Sets altitude of threshold point
        """
        self.point.setAltitude(alt)

    def getPoint(self):
        """
        Returns runway threshold point
        """
        return self.point

    def getRoute(self):
        """
        Returns runway threshold point
        """
        return [self.point]

    def both(self):
        """
        Returns neutral representation of runway in case of multiple parallel runways
        """
        if self.runway[-1] in list("LR"):  # "LRC"? NNL + NNR -> NNB, I don't know if there is a NNC?
            return self.runway[:-1] + "B"
        return "ALL"

    def prepareRestrictions(self, route):
        logger.debug(f"RWY has no route data to prepare for restrictions")


class CIFP:
    """
    This class loads all procedures for a given airport.
    """

    def __init__(self, icao: str):
        self.icao = icao
        self.airac_cycle = None
        self.available = False

        self.SIDS = {}
        self.STARS = {}
        self.APPCHS = {}
        self.RWYS = {}

        self.basename = DEFAULT_DATA_DIR
        fn = os.path.join(CUSTOM_DATA_DIR, "CIFP")
        if os.path.isdir(fn):
            logger.debug(f"CIFP custom data directory exist, using it")
            self.basename = CUSTOM_DATA_DIR

        self.loadFromFile()

    def getKey(self):
        """
        Returns airport ICAO name for this set of procedure.
        """
        return self.icao

    def getInfo(self):
        """
        Returns instance information.
        """
        return {
            "type": "CIFP",
            "terminal": self.icao,
            "runways": list(self.RWYS.keys()),
            "stars": dict([(k, list(v.keys())) for k, v in self.STARS.items()]),
            "approaches": dict([(k, list(v.keys())) for k, v in self.APPCHS.items()]),
            "sids": dict([(k, list(v.keys())) for k, v in self.SIDS.items()]),
        }

    def loadFromFile(self):
        """
        Loads Coded Instrument Flight Procedures for one airport

        :returns:   { description_of_the_return_value }
        :rtype:     { return_type_description }
        """
        cipf_filename = os.path.join(self.basename, "CIFP", self.icao + ".dat")
        if not os.path.exists(cipf_filename):
            logger.warning(f"no procedure file for {self.icao}")
            return (False, f"CIFP:loadFromFile: file not found {cipf_filename}")

        logger.debug(f"procedure CIFP file {cipf_filename}")
        self.available = True
        cifp_fp = open(cipf_filename, "r")
        line = cifp_fp.readline()
        prevline = None
        procedures = {"SID": {}, "STAR": {}, "APPCH": {}, "RWY": {}}

        while line:
            cifpline = ProcedureData(line.strip())
            procty = cifpline.proc()
            procname = cifpline.name().strip()  # RWY NAME IS  ALWAYS RWNNL, L can be a space.
            procrwy = cifpline.runway()

            if procty == "PRDAT":  # continuation of last line of current procedure
                if prevline is not None:
                    prevline.addData(cifpline)
                else:
                    logger.warning("received PRDAT but no procedure to add to")
            else:
                if procty == "RWY":
                    procedures[procty][procname] = RWY(procname, self.icao)
                    procedures[procty][procname].add(cifpline)
                else:
                    if procrwy not in procedures[procty].keys():
                        procedures[procty][procrwy] = {}
                    if procname not in procedures[procty][procrwy].keys():
                        if procty == "SID":
                            procedures[procty][procrwy][procname] = SID(procname)
                        elif procty == "STAR":
                            procedures[procty][procrwy][procname] = STAR(procname)
                        elif procty == "APPCH":
                            procedures[procty][procrwy][procname] = APPCH(procname)
                        else:
                            logger.warning("invalid procedure %s", procty)

                    if procname in procedures[procty][procrwy].keys():
                        procedures[procty][procrwy][procname].add(cifpline)
                    else:
                        logger.warning("procedure not created %s", procty)

            prevline = cifpline
            line = cifp_fp.readline()

        # User friendlier:
        self.SIDS = procedures["SID"]
        self.STARS = procedures["STAR"]
        self.APPCHS = procedures["APPCH"]
        self.RWYS = procedures["RWY"]

        # pair runways
        self.pairRunways()

        ## Print result
        # for k, v in procedures.items():
        #     if k == "RWY":
        #         logger.debug(f"{k}: {v.keys()}")
        #     else:
        #         for r, p in v.items():
        #             logger.debug(f"{k} {r}: {p.keys()}")

        # details:
        # for p in procedures[procty]:
        #    logger.debug("%s: %s %s" % (procty, procedures[procty][p].runway, p))
        return (True, "CIFP:loadFromFile: loaded")

    def pairRunways(self):
        """
        Pairs runways in opposite direction.
        """
        if len(self.RWYS) == 2:
            rwk = list(self.RWYS.keys())
            self.RWYS[rwk[0]].end, self.RWYS[rwk[1]].end = (self.RWYS[rwk[1]], self.RWYS[rwk[0]])
            logger.debug(f"{self.icao}: {self.RWYS[rwk[0]].name} and {self.RWYS[rwk[1]].name} paired")
        else:
            logger.debug(f"{self.icao}: pairing {self.RWYS.keys()}")
            for k, r in self.RWYS.items():
                if r.end is None:
                    rh = int(k[2:4])
                    ri = rh + 18
                    if ri > 36:
                        ri = ri - 36
                    rl = k[-1]  # {L|R|C|<SPC>}
                    rw = "RW%02d" % ri
                    if rl == "L":
                        rw = rw + "R"
                    elif rl == "R":
                        rw = rw + "L"
                    elif rl == "C":
                        rw = rw + "C"
                    # elif rl in [" ", "@"]:
                    #     rw = rw
                    # else:
                    #     rw = rw
                    if rw in self.RWYS.keys():
                        r.end = self.RWYS[rw]
                        self.RWYS[rw].end = r
                        uuid = k.replace("RW", "") + "-" + rw.replace("RW", "") if k < rw else rw.replace("RW", "") + "-" + k.replace("RW", "")
                        r.uuid = uuid
                        r.end.uuid = uuid
                        logger.debug(f"{self.icao}: {r.name} and {rw} paired as {uuid}")
                    else:
                        logger.warning(f"{self.icao}: {rw} ont found to pair {r.name}")
        # bearing and length
        for k, r in self.RWYS.items():
            if r.end is not None and r.getPoint() is not None and r.end.getPoint() is not None:
                r.bearing = bearing(r.getPoint(), r.end.getPoint())
                r.length = distance(r.getPoint(), r.end.getPoint(), "m")
            else:
                logger.warning(f"runway {k} for {self.icao} has missing threshold")
            # else:
            #     apt = Airport.findICAO(self.icao)
            #     if apt is not None:
            #         r.point = NamedPointWithRestriction(
            #             ident=line.params[0],
            #             region=self.icao[0:2],
            #             airport=self.icao,
            #             pointtype="RWY",
            #             lat=apt.coords()[1],
            #             lon=apt.coords()[0]
            #         )
            #         logger.warning(f"runway {k} for {self.icao} has no threshold, replaced by airport coordinates.")

    def getRoute(self, procedure: Procedure, airspace: Aerospace):
        """
        Get array of vertices representing the supplied procedure.

        :param      procedure:  The procedure
        :type       procedure:  Procedure
        :param      airspace:   The airspace
        :type       airspace:   Aerospace
        """
        return procedure.getRoute(airspace)

    def getRunway(self):
        """
        Returns a random runway from RWY list.
        """
        # Random for now, can use some logic if necessary.
        rwy = random.choice(list(self.RWYS.keys()))
        return {rwy: self.RWYS[rwy]}

    def getRunways(self):
        """
        Returns all runway thresholds.
        """
        ret = {}
        for k, v in self.RWYS.items():
            if v.has_latlon():
                ret[k] = v
        return ret

    def getOperationalRunways(self, wind_dir: float):
        """
        Get a runway opposite to the supplied wind direction.
        If there is no wind, a random runway is selected.

        :param      wind_dir:  The wind dir
        :type       wind_dir:  float
        """
        if wind_dir is None:
            logger.warning(f"{self.icao} no wind direction, using all runways")
            return self.getRunways()

        max1 = wind_dir - 90
        if max1 < 0:
            max1 = max1 + 360
        max1 = int(max1 / 10)
        max2 = wind_dir + 90
        if max2 > 360:
            max2 = max2 - 360
        max2 = int(max2 / 10)
        if max1 > max2:
            max1, max2 = max2, max1

        # logger.debug("%f %d %d" % (wind_dir, max1, max2))
        rops = {}
        if wind_dir > 90 and wind_dir < 270:
            for rwy in self.RWYS.keys():
                # logger.debug("%s %d" % (rwy, int(rwy[2:4])))
                rw = int(rwy[2:4])
                if rw >= max1 and rw < max2:
                    # logger.debug("added %s" % rwy)
                    rops[rwy] = self.RWYS[rwy]
        else:
            for rwy in self.RWYS.keys():
                # logger.debug("%s %d" % (rwy, int(rwy[2:4])))
                rw = int(rwy[2:4])
                if rw < max1 or rw >= max2:
                    # logger.debug("added %s" % rwy)
                    rops[rwy] = self.RWYS[rwy]

        if len(rops.keys()) == 0:
            logger.warning(f"{self.icao} could not find runway for operations")

        logger.info(f"{self.icao} wind direction is {wind_dir:f}, runway in use: {rops.keys()}")
        return rops
