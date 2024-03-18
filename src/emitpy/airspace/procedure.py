"""
CIFP is a collection of standard instrument arrival and departure procedures for an airport.
It also contains runways, approches and final approaches.
A couple of helper classes help deal with CIFP file parsing.
"""

from __future__ import annotations
import os
import logging
import random
from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, List

from emitpy.constants import ID_SEP
from emitpy.geo.turf import distance, bearing
from emitpy.utils import convert, show_path
from emitpy.parameters import XPLANE_DIR
from .restriction import Restriction, NamedPointWithRestriction

# Where to find CIFP files
DEFAULT_DATA_DIR = os.path.join(XPLANE_DIR, "Resources", "default data")
CUSTOM_DATA_DIR = os.path.join(XPLANE_DIR, "Custom Data")

logger = logging.getLogger("Procedure")


class PROC_TYPE(Enum):
    SID = "sid"
    STAR = "star"
    APPCH = "approach"
    RWY = "runway"


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
        self.procedure: str | None = None
        self.data: List[ProcedureData] = []
        self.params = []
        a = line.split(":")
        if len(a) < 2:
            logger.debug("invalid line '%s'", line)
        else:
            self.procedure = a[0]
            self.params = a[1].split(",")
        if len(self.params) == 0:
            logger.debug("invalid line '%s', no params", line)

    def proc(self) -> str:
        """
        Returns the procedure type (SID, STAR, RWY, APPCH)
        """
        return self.procedure

    def name(self) -> str:
        """
        Returns the procedure name, if present
        """
        if self.proc() == "RWY":
            return self.param(PROC_DATA.SEQ_NR)
        return self.params[2]

    def addData(self, data: ProcedureData):
        """
        Adds a line of procedure data

        :param      data:  The data
        :type       data:  { type_description }
        """
        return self.data.append(data)

    def seq(self) -> int:
        """
        Returns the procedure data line sequence number
        """
        if self.proc() in ("RWY", "PRDAT"):
            return 0
        return int(self.param(PROC_DATA.SEQ_NR))

    def line(self) -> str:
        """
        Returns the whole procedure line
        """
        return ",".join(self.params)

    def param(self, name: PROC_DATA) -> str:
        """
        Returns the requested procedure data or parameter.
        Name of parameter is coded in PROC_DATA enum.

        :param      name:  The name
        :type       name:  PROC_DATA
        """
        return self.params[name.value]

    def runway(self) -> str:
        """
        This function reports the runway to which the procedure applies.
        IT IS NOT NECESSARILY A REAL RUNWAY NAME.
        For exemple,
        - if a function relates to all runways, this procedure will return ALL
        - if a function relates to both NNL and NNR runways, this procedure will return NNB (both)
        This is taken into account when selecting procedures for a given runway.
        """
        if self.proc() == "RWY":
            return self.param(PROC_DATA.SEQ_NR)
        if self.proc() == "APPCH":
            s = self.param(PROC_DATA.PROCEDURE_IDENT)
            l = -3 if s[-1] in list("LCR") else -2
            return "RW" + s[l:]
        return self.param(PROC_DATA.TRANS_IDENT)

    def getRestriction(self) -> Restriction:
        altmin = convert.cifp_alt_in_ft(self.param(PROC_DATA._MIN_ALT1))
        altmax = convert.cifp_alt_in_ft(self.param(PROC_DATA._MIN_ALT2))
        speedlim = convert.cifp_speed(self.param(PROC_DATA.SPEED_LIMIT))
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

    def __init__(self, name: str) -> None:
        self.name = name
        self.runway: str | None = None
        self.route: Dict[int, ProcedureData] = {}  # list of CIFP lines
        self._valid = True

    def add(self, line: ProcedureData) -> None:
        """
        Adds a line of procedure data to the procedure

        :param      line:  The line
        :type       line:  ProcedureData
        """
        if len(self.route) == 0:  # First time, sets runway CIFP name
            self.runway = line.runway()
        self.route[line.seq()] = line

    def getNamedPointWithRestriction(self, airspace, vertex, restriction: Restriction) -> NamedPointWithRestriction | None:
        p = airspace.getNamedPoint(vertex)
        if p is not None:
            pointtype = p.id.split(ID_SEP)[-2]
            u = NamedPointWithRestriction(ident=p.ident, region=p.region, airport=p.airport, pointtype=pointtype, lat=p.lat(), lon=p.lon())
            u.combine(restriction)
            logger.debug(f"{type(self).__name__} {self.name}: {vertex} ({u.getRestrictionDesc(True)})")
            return u
        logger.warning(f"no vertex named {vertex}")
        return None

    def getEntrySpeedAndAlt(self):
        return (0, 0)

    def getExitSpeedAndAlt(self):
        return (0, 0)

    @abstractmethod
    def getRoute(self, airspace: Aerospace) -> List["Vertex" | NamedPointWithRestriction]:
        pass

    @abstractmethod
    def prepareRestrictions(self, route) -> None:
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
                    logger.warning(f"SID:vertex ambiguous {vid} ({len(vtxs)}, {vtxs})")
                else:
                    logger.warning("SID:vertex not found %s", vid)

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
                    v.setProp("_speed_min", v.restricted_speed)
                    v.setProp("_speed_max", v.restricted_speed)
                    v.setProp("_speed_target", v.restricted_speed)  # mandatory to pass wp at that speed
                elif spd_desc == "+":
                    v.setProp("_speed_min", v.restricted_speed)
                elif spd_desc == "-":
                    v.setProp("_speed_max", v.restricted_speed)
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


class STAR(Procedure):
    """
    A Standard Terminal Arrival Route is a special instance of a Procedure.
    """

    def __init__(self, name: str):
        Procedure.__init__(self, name)

    def getEntrySpeedAndAlt(self, default: int = 6000):
        return (0, convert.feet_to_meters(default))

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
                    logger.warning("STAR:vertex ambiguous %s (%d, %s)" % (vid, len(vtxs), vtxs))
                else:
                    logger.warning("STAR:vertex not found %s", vid)

        self.prepareRestrictions(a)
        return a

    def prepareRestrictions(self, route):
        # Speed
        # print("*><-" * 40)
        curr_limit = None
        for i in range(len(route)):
            v = route[i]
            if v.hasSpeedRestriction():
                # print(">>> has speed restriction", v.ident, v.getSpeedRestrictionDesc())
                v.setProp("_restricted_speed", v.getSpeedRestrictionDesc())
                spd_desc = v.speed_restriction_type
                if spd_desc in [" ", "@"]:
                    v.setProp("_speed_min", v.restricted_speed)
                    v.setProp("_speed_max", v.restricted_speed)
                    v.setProp("_speed_target", v.restricted_speed)
                elif spd_desc == "+":
                    v.setProp("_speed_min", v.restricted_speed)
                elif spd_desc == "-":
                    v.setProp("_speed_max", v.restricted_speed)
                curr_limit = v
            elif curr_limit is not None:  # carry restriction forward
                # print(">>> carry forward speed restriction", v.ident, curr_limit.getSpeedRestrictionDesc())
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
                # print(">>> has altitude restriction", v.ident, v.getAltitudeRestrictionDesc())
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

    def getEntrySpeedAndAlt(self, default: int = 3000):
        return (0, convert.feet_to_meters(default))

    def getExitSpeedAndAlt(self, default: int = 2000):
        return (0, convert.feet_to_meters(default))

    def is_final_fix_point(self, vertex):
        code_raw = vertex.param(PROC_DATA.DESC_CODE)
        return len(code_raw) > 4 and code_raw[3] in ["E", "F"]

    def getFinalFixAltInFt(self, default: int | None = 2000) -> int | None:
        alt = default
        has_one = False
        for v in self.route.values():
            if self.is_final_fix_point(v):
                if v.hasAltitudeRestriction():
                    has_one = True
                    logger.debug(f"final fix restriction {v.getAltitudeRestrictionDesc()}")
                    alt_desc = v.alt_restriction_type
                    if alt_desc in [" ", "@"]:
                        alt = v.alt1
                    elif alt_desc == "B":
                        if v.alt1 > v.alt2:  # keep the lowest
                            alt = v.alt2
                        else:
                            alt = v.alt1
                    elif alt_desc in ["+"]:
                        alt = v.alt1
                    elif alt_desc in ["C", "D"]:
                        alt = v.alt2
                    elif alt_desc == "-":
                        alt = v.alt1
                    logger.debug(f"final fix altitude: {alt}ft")
                else:
                    logger.debug(f"final fix has no restriction")
        if not has_one:
            logger.debug(f"no final fix in approach, using default alt {default}ft")
        return alt

    def getLastAltitudeRestriction(self, default: int | None = 2000) -> int | None:
        """@todo: THIS IS NOT CORRECT"""
        last_restriction = None
        route = sorted(self.route.values(), key=lambda x: x.seq(), reverse=True)
        for v in route:
            # if last_restriction is not None:
            #     continue  # break?
            code_raw = v.param(PROC_DATA.DESC_CODE)
            # Need to exclude wp that are part of missed approach procedure/path
            is_miss_approach = (len(code_raw) > 2 and code_raw[2] == "M") or (len(code_raw) > 3 and (code_raw[2] == "M" or code_raw[3] == "M"))
            code = code_raw[0]
            if code == "E" and not is_miss_approach:
                # print(v.seq(), v.line())
                restriction = v.getRestriction()
                if restriction is not None:
                    # print(">>>", restriction.getRestrictionDesc())
                    if restriction.hasAltitudeRestriction() and last_restriction is None:
                        last_restriction = restriction.alt1
            else:
                print("missed approach", v.seq(), v.line())
        if last_restriction is None:
            logger.debug(f"no last altitude restriction, using default alt {default}ft")
            last_restriction = default
        return last_restriction

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
            # print("route", v.seq())
            code_raw = v.param(PROC_DATA.DESC_CODE)
            # Need to exclude wp that are part of missed approach procedure/path
            is_miss_approach = (len(code_raw) > 2 and code_raw[2] == "M") or (len(code_raw) > 3 and (code_raw[2] == "M" or code_raw[3] == "M"))
            code = code_raw[0]
            if code == "E" and not is_miss_approach and not interrupted:
                vid = v.param(PROC_DATA.ICAO_CODE) + ":" + v.param(PROC_DATA.FIX_IDENT) + ":"
                # logger.debug("APPCH:getRoute: %s" % vid)
                vtxs = list(filter(lambda x: x.startswith(vid), airspace.vert_dict.keys()))
                if len(vtxs) > 0 and len(vtxs) < 3:  # there often is both a VOR and a DME at same location
                    a.append(self.getNamedPointWithRestriction(airspace=airspace, vertex=vtxs[0], restriction=v.getRestriction()))
                elif len(vtxs) > 2:
                    logger.warning("APPCH:vertex ambiguous %s (%d, %s)" % (vid, len(vtxs), vtxs))
                else:
                    logger.warning("APPCH:vertex not found %s", vid)
            else:
                if not interrupted:
                    logger.debug(
                        "APPCH:getRoute: interrupted %s", ("" if len(v.param(PROC_DATA.FIX_IDENT).strip()) == 0 else (f" at {v.param(PROC_DATA.FIX_IDENT)} "))
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
                # print(">>> has speed restriction", v.ident, v.getSpeedRestrictionDesc())
                v.setProp("_restricted_speed", v.getSpeedRestrictionDesc())
                spd_desc = v.speed_restriction_type
                if spd_desc in [" ", "@"]:
                    v.setProp("_speed_min", v.restricted_speed)
                    v.setProp("_speed_max", v.restricted_speed)
                    v.setProp("_speed_target", v.restricted_speed)
                elif spd_desc == "+":
                    v.setProp("_speed_min", v.restricted_speed)
                elif spd_desc == "-":
                    v.setProp("_speed_max", v.restricted_speed)
                curr_limit = v
            elif curr_limit is not None:  # carry restriction forward
                # print(">>> carry forward speed restriction", v.ident, curr_limit.getSpeedRestrictionDesc())
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
                # print(">>> has altitude restriction", v.ident, v.getAltitudeRestrictionDesc())
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
        self.point: NamedPointWithRestriction | None = None
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
            self.setAltitude(convert.feet_to_meters(float(self.route[0].params[3])))
        else:
            logger.warning(f"Runway {self.runway} has no threshold")
            self._valid = False

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
        return convert.dms_to_dd(latstr[1:3], latstr[3:5], int(latstr[5:9]) / 100, latstr[0])

    def getLongitude(self):
        """
        Returns longitude of threshold point
        """
        lonstr = self.route[0].params[8]
        return convert.dms_to_dd(lonstr[1:4], lonstr[4:6], int(lonstr[6:10]) / 100, lonstr[0])

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

        self.SIDS: Dict[str, SID] = {}
        self.STARS: Dict[str, STAR] = {}
        self.APPCHS: Dict[str, APPCH] = {}
        self.RWYS: Dict[str, RWY] = {}
        self.BYNAME: Dict[str, Procedure] = {}  # this is weak temporary construct to quicly locate procedures see flight.force_procedures().

        self.basename = DEFAULT_DATA_DIR
        fn = os.path.join(CUSTOM_DATA_DIR, "CIFP")
        if os.path.isdir(fn):
            logger.debug(f"CIFP custom data directory {show_path(CUSTOM_DATA_DIR)} exist, using it")
            self.basename = CUSTOM_DATA_DIR
        else:
            logger.debug(f"CIFP using {show_path(DEFAULT_DATA_DIR)}")
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

        logger.debug(f"procedure CIFP file {show_path(cipf_filename)}")
        self.available = True
        cifp_fp = open(cipf_filename, "r")
        line = cifp_fp.readline()
        prevline = None
        sids: Dict[str, SID] = {}
        stars: Dict[str, STAR] = {}
        appch: Dict[str, APPCH] = {}
        rwys: Dict[str, RWY] = {}
        procedures = {"SID": sids, "STAR": stars, "APPCH": appch, "RWY": rwys}

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
                            self.BYNAME[procname] = procedures[procty][procrwy][procname]
                        elif procty == "STAR":
                            procedures[procty][procrwy][procname] = STAR(procname)
                            self.BYNAME[procname] = procedures[procty][procrwy][procname]
                        elif procty == "APPCH":
                            procedures[procty][procrwy][procname] = APPCH(procname)
                            self.BYNAME[procname] = procedures[procty][procrwy][procname]
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

        self.remove_invalid()

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

    def remove_invalid(self):
        for p in list(self.RWYS.values()):
            if not p._valid:
                del self.RWYS[p.name]
                logger.warning(f"removed invalid runway {p.name}")
        for r in self.SIDS.keys():
            for p in list(self.SIDS[r].values()):
                if not p._valid:
                    del self.BYNAME[p.name]
                    del self.SIDS[p.name]
                    logger.warning(f"removed invalid SID {p.name}")
        for r in self.STARS.keys():
            for p in list(self.STARS[r].values()):
                if not p._valid:
                    del self.BYNAME[p.name]
                    del self.STARS[p.name]
                    logger.warning(f"removed invalid STAR {p.name}")
        for r in self.APPCHS.keys():
            for p in list(self.APPCHS[r].values()):
                if not p._valid:
                    del self.BYNAME[p.name]
                    del self.APPCHS[p.name]
                    logger.warning(f"removed invalid APPCH {p.name}")

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

    def getOperationalRunways(self, wind_dir: float) -> Dict[str, RWY]:
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
        rops: Dict[str, RWY] = {}
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
