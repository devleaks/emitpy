"""
CIFP is a collection of standard instrument arrival and departure procedures for an airport.
It also contains runways, approches and final approaches.
A couple of helper classes help deal with CIFP file parsing.
"""
import os
import logging
import random
from enum import Enum

from turfpy.measurement import distance, bearing

from emitpy.utils import ConvertDMSToDD, FT
from emitpy.parameters import XPLANE_DIR
from .airspace import Airspace, RestrictedSignificantPoint

DEFAULT_DATA_DIR = os.path.join(XPLANE_DIR, "Resources", "default data")
CUSTOM_DATA_DIR  = os.path.join(XPLANE_DIR, "Custom Data")


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
    ALT_DESC = 22
    _MIN_ALT1 = 23
    _MIN_ALT2 = 24
    TRANS_ALTITUDE_LEVEL = 25
    _SPEED_LIM_DESC = 26
    SPEED_LIMIT = 27
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
            logger.debug(":__init__: invalid line '%s'", line)
        else:
            self.procedure = a[0]
            self.params = a[1].split(",")
        if len(self.params) == 0:
            logger.debug(":__init__: invalid line '%s', no params", line)


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


class Procedure:
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


class SID(Procedure):
    """
    A Standard Instrument Departure is a special instance of a Procedure.
    """
    def __init__(self, name: str):
        Procedure.__init__(self, name)

    def getRoute(self, airspace: Airspace):
        """
        Returns an array of vertices from the Airspace
        that follow the SID

        :param      airspace:  The airspace
        :type       airspace:  Airspace
        """
        a = []
        for v in self.route.values():
            fid = v.param(PROC_DATA.FIX_IDENT).strip()
            if len(fid) > 0:
                vid = v.param(PROC_DATA.ICAO_CODE) + ":" + v.param(PROC_DATA.FIX_IDENT) + ":"
                logger.debug("SID:getRoute: %s" % vid)
                vtxs = list(filter(lambda x: x.startswith(vid), airspace.vert_dict.keys()))
                if len(vtxs) > 0 and len(vtxs) < 3:  # there often is both a VOR and a DME at same location, we keep either one
                    a.append(airspace.getSignificantPoint(vtxs[0]))
                elif len(vtxs) > 2:
                    logger.warning("SID:getRoute: vertex ambiguous %s (%d, %s)" % (vid, len(vtxs), vtxs))
                else:
                    logger.warning("SID:getRoute: vertex not found %s", vid)
        return a


class STAR(Procedure):
    """
    A Standard Terminal Arrival Route is a special instance of a Procedure.
    """
    def __init__(self, name: str):
        Procedure.__init__(self, name)

    def getRoute(self, airspace: Airspace):
        """
        Returns an array of vertices from the Airspace
        that follow the STAR

        :param      airspace:  The airspace
        :type       airspace:  Airspace
        """
        a = []
        for v in self.route.values():
            fid = v.param(PROC_DATA.FIX_IDENT).strip()
            if len(fid) > 0:
                vid = v.param(PROC_DATA.ICAO_CODE) + ":" + v.param(PROC_DATA.FIX_IDENT) + ":"
                logger.debug("STAR:getRoute: %s" % vid)
                vtxs = list(filter(lambda x: x.startswith(vid), airspace.vert_dict.keys()))
                if len(vtxs) > 0 and len(vtxs) < 3:  # there often is both a VOR and a DME at same location
                    a.append(airspace.getSignificantPoint(vtxs[0]))
                elif len(vtxs) > 2:
                    logger.warning("STAR:getRoute: vertex ambiguous %s (%d, %s)" % (vid, len(vtxs), vtxs))
                else:
                    logger.warning("STAR:getRoute: vertex not found %s", vid)
        return a


class APPCH(Procedure):
    """
    Approach procedure to runway.

    APPCH:030,D,D16L, ,MD16L,OT,P,C,E  M, ,   ,CF, ,DOH,OT,D, ,      ,3460,0056,1660,0063, ,00995,     ,     , ,   ,-300,   , , , , , ,0, ,S;

    """
    def __init__(self, name: str):
        Procedure.__init__(self, name)

    def getRoute(self, airspace: Airspace):
        """
        Returns an array of vertices from the Airspace
        that follow the approach.

        :param      airspace:  The airspace
        :type       airspace:  Airspace
        """
        interrupted = False
        a = []
        for v in self.route.values():
            code = v.param(PROC_DATA.DESC_CODE)[0]
            if code == "E" and not interrupted:
                vid = v.param(PROC_DATA.ICAO_CODE) + ":" + v.param(PROC_DATA.FIX_IDENT) + ":"
                logger.debug(":getRoute: %s" % vid)
                vtxs = list(filter(lambda x: x.startswith(vid), airspace.vert_dict.keys()))
                if len(vtxs) > 0 and len(vtxs) < 3:  # there often is both a VOR and a DME at same location
                    a.append(airspace.getSignificantPoint(vtxs[0]))
                elif len(vtxs) > 2:
                    logger.warning("APPCH:getRoute: vertex ambiguous %s (%d, %s)" % (vid, len(vtxs), vtxs))
                else:
                    logger.warning("APPCH:getRoute: vertex not found %s", vid)
            else:
                if not interrupted:
                    logger.debug("APPCH:getRoute: interrupted %s", "" if len(v.param(PROC_DATA.FIX_IDENT).strip()) == 0 else (f" at {v.param(PROC_DATA.FIX_IDENT)} "))
                interrupted = True

            # print("%s %s: %d: %s [%s], A: %s [%s,%s], S: %s %s " % (type(self).__name__, self.name, v,
            #     self.route[v].param("FIX IDENT"),
            #     self.route[v].param("DESC CODE"),
            #     self.route[v].param("ALT DESC"),
            #     self.route[v].param("_MIN ALT 1"),
            #     self.route[v].param("_MIN ALT 2"),
            #     self.route[v].param("_SPEED LIM DESC"),
            #     self.route[v].param("SPEED LIMIT"),
            #     ))
        return a


class RWY(Procedure):
    """
    A runway for starting a SID or terminating a STAR.
    We distinguish the "aeronautical" RWY (in Airspace.Procedure) from the gegraphical/geometrical Runway (in Geo.Runway)

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
            logger.warning(":add: Cannot add to an already defined runway")
            return


        #     0     1     2      3     4 5    6 7             8          9
        # RWY:RW16L,     ,      ,00013, ,IDE ,3,   ;N25174597,E051363196,0000;
        self.route[0] = line
        if self.has_latlon():
            self.point = RestrictedSignificantPoint(
                ident=line.params[0],
                region=self.airport[0:2],
                airport=self.airport,
                pointtype="RWY",
                lat=self.getLatitude(),
                lon=self.getLongitude()
            )
            self.setAltitude(float(self.route[0].params[3]) * FT)
        else:
            logger.warning(f":add: Runway {self.runway} has no threshold")


    def has_latlon(self):
        """
        Returns whether the RWY procedure has latitude and longitude of threshold point
        """
        return (self.route[0].params[7].split(";")[1] != '') and (self.route[0].params[8] != '')

    def getLatitude(self):
        """
        Returns latitude of threshold point
        """
        latstr = self.route[0].params[7].split(";")[1]
        return ConvertDMSToDD(latstr[1:3], latstr[3:5], int(latstr[5:9])/100, latstr[0])

    def getLongitude(self):
        """
        Returns longitude of threshold point
        """
        lonstr = self.route[0].params[8]
        return ConvertDMSToDD(lonstr[1:4], lonstr[4:6], int(lonstr[6:10])/100, lonstr[0])

    def setAltitude(self, alt):
        """
        Sets altitude of threshold point
        """
        if len(self.point["geometry"]["coordinates"]) > 2:
            self.point["geometry"]["coordinates"][2] = alt
        else:
            self.point["geometry"]["coordinates"].append(alt)

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
        fn = os.path.join(CUSTOM_DATA_DIR, "earth_nav.dat")
        if os.path.exists(fn):
            logger.debug(f":init: custom data directory exist, using it")
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
            "sids": list(self.SIDS.keys()),
            "stars": list(self.STARS.keys()),
            "sids": list(self.SIDS.keys()),
            "approaches": list(self.APPCHS.keys()),
            "runways": list(self.RWYS.keys())
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

        self.available = True
        cifp_fp = open(cipf_filename, "r")
        line = cifp_fp.readline()
        prevline = None
        procedures = {
            "SID": {},
            "STAR": {},
            "APPCH": {},
            "RWY": {}
        }

        while line:
            cifpline = ProcedureData(line.strip())
            procty = cifpline.proc()
            procname = cifpline.name().strip()  # RWY NAME IS  ALWAYS RWNNL, L can be a space.
            procrwy = cifpline.runway()

            if procty == "PRDAT":  # continuation of last line of current procedure
                if prevline is not None:
                    prevline.addData(cifpline)
                else:
                    logger.warning(":loadCIFP: received PRDAT but no procedure to add to")
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
                            logger.warning(":loadCIFP: invalid procedure %s", procty)

                    if procname in procedures[procty][procrwy].keys():
                        procedures[procty][procrwy][procname].add(cifpline)
                    else:
                        logger.warning(":loadCIFP: procedure not created %s", procty)

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
        #         logger.debug(f":loadFromFile: {k}: {v.keys()}")
        #     else:
        #         for r, p in v.items():
        #             logger.debug(f":loadFromFile: {k} {r}: {p.keys()}")

            # details:
            # for p in procedures[procty]:
            #    logger.debug(":CIFP: %s: %s %s" % (procty, procedures[procty][p].runway, p))
        return (True, "CIFP:loadFromFile: loaded")

    def pairRunways(self):
        """
        Pairs runways in opposite direction.
        """
        if len(self.RWYS) == 2:
            rwk = list(self.RWYS.keys())
            self.RWYS[rwk[0]].end, self.RWYS[rwk[1]].end = self.RWYS[rwk[1]], self.RWYS[rwk[0]]
            logger.debug(f":pairRunways: {self.icao}: {self.RWYS[rwk[0]].name} and {self.RWYS[rwk[1]].name} paired")
        else:
            logger.debug(f":pairRunways: {self.icao}: pairing {self.RWYS.keys()}")
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
                    # elif rl == " ":
                    #     rw = rw
                    # else:
                    #     rw = rw
                    if rw in self.RWYS.keys():
                        r.end = self.RWYS[rw]
                        self.RWYS[rw].end = r
                        uuid = k.replace("RW", "")+"-"+rw.replace("RW", "") if k < rw else rw.replace("RW", "")+"-"+k.replace("RW", "")
                        r.uuid = uuid
                        r.end.uuid = uuid
                        logger.debug(f":pairRunways: {self.icao}: {r.name} and {rw} paired as {uuid}")
                    else:
                        logger.warning(f":pairRunways: {self.icao}: {rw} ont found to pair {r.name}")
        # bearing and length
        for k, r in self.RWYS.items():
            if r.end is not None and r.getPoint() is not None and r.end.getPoint() is not None:
                r.bearing = bearing(r.getPoint(), r.end.getPoint())
                r.length = distance(r.getPoint(), r.end.getPoint(), "m")
            else:
                logger.warning(f":pairRunways: runway {k} for {self.icao} has missing threshold")
            # else:
            #     apt = Airport.findICAO(self.icao)
            #     if apt is not None:
            #         r.point = RestrictedSignificantPoint(
            #             ident=line.params[0],
            #             region=self.icao[0:2],
            #             airport=self.icao,
            #             pointtype="RWY",
            #             lat=apt["geometry"]["coordinates"][1],
            #             lon=apt["geometry"]["coordinates"][0]
            #         )
            #         logger.warning(f":pairRunways: runway {k} for {self.icao} has no threshold, replaced by airport coordinates.")


    def getRoute(self, procedure: Procedure, airspace: Airspace):
        """
        Get array of vertices representing the supplied procedure.

        :param      procedure:  The procedure
        :type       procedure:  Procedure
        :param      airspace:   The airspace
        :type       airspace:   Airspace
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
            logger.warning(f":getOperationalRunways: {self.icao} no wind direction, using all runways")
            return self.getRunways()

        max1 = wind_dir - 90
        if max1 < 0:
            max1 = max1 + 360
        max1 = int(max1/10)
        max2 = wind_dir + 90
        if max2 > 360:
            max2 = max2 - 360
        max2 = int(max2/10)
        if max1 > max2:
            max1, max2 = max2, max1

        # logger.debug(":_computeOperationalRunways: %f %d %d" % (wind_dir, max1, max2))
        rops = {}
        if wind_dir > 90 and wind_dir < 270:
            for rwy in self.RWYS.keys():
                # logger.debug(":_computeOperationalRunways: %s %d" % (rwy, int(rwy[2:4])))
                rw = int(rwy[2:4])
                if rw >= max1 and rw < max2:
                    # logger.debug(":_computeOperationalRunways: added %s" % rwy)
                    rops[rwy] = self.RWYS[rwy]
        else:
            for rwy in self.RWYS.keys():
                # logger.debug(":_computeOperationalRunways: %s %d" % (rwy, int(rwy[2:4])))
                rw = int(rwy[2:4])
                if rw < max1 or rw >= max2:
                    # logger.debug(":_computeOperationalRunways: added %s" % rwy)
                    rops[rwy] = self.RWYS[rwy]

        if len(rops.keys()) == 0:
            logger.warning(f":getOperationalRunways: {self.icao} could not find runway for operations")

        logger.info(f":getOperationalRunways: {self.icao} wind direction is {wind_dir:f}, runway in use: {rops.keys()}")
        return rops

