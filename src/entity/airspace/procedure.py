"""
A Flight Route is an array of ProcedurePoint.
A ProcedurePoint is either a waypoint or just a coordinate with mandatory properties.
"""
import os
import logging
from enum import Enum

from .airspace import Airspace, RestrictedControlledPoint
from ..utils import ConvertDMSToDD

from ..parameters import DATA_DIR

SYSTEM_DIRECTORY = os.path.join(DATA_DIR, "x-plane")

logger = logging.getLogger("Airport")


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
    # CIFP line for this airport
    def __init__(self, line):
        self.procedure = None
        self.data = []
        self.params = []
        a = line.split(":")
        if len(a) < 2:
            logging.debug("ProcedureData::__init__: invalid line '%s'", line)
        else:
            self.procedure = a[0]
            self.params = a[1].split(",")
        if len(self.params) == 0:
            logging.debug("ProcedureData::__init__: invalid line '%s'", line)

    def proc(self):
        return self.procedure

    def name(self):
        if self.proc() == "RWY":
            return self.params[0]
        return self.params[2]

    def addData(self, data):
        return self.data.append(data)

    def seq(self):
        if self.proc() in ("RWY", "PRDAT"):
            return 0
        return int(self.params[0])

    def line(self):
        return ",".join(self.params)

    def param(self, name: PROC_DATA):
        return self.params[name.value]


class Procedure:
    """
    A Procedure is a named array of ProcedureData (lines or routes)
    Abstract class.
    """
    def __init__(self, name: str):
        self.name = name
        self.runway = None
        self.route = {}  ## list of CIFP lines

    def add(self, line: ProcedureData):
        if len(self.route) == 0:  # First time, sets runway CIFP name
            if line.proc() == "RWY":
                self.runway = self.name
            elif line.proc() == "APPCH":
                self.runway = "RW" + line.param(PROC_DATA.PROCEDURE_IDENT)[-3:]
            else:
                self.runway = line.param(PROC_DATA.TRANS_IDENT)
        self.route[line.seq()] = line


class SID(Procedure):
    """
    A Standard Instrument Departure is a special instance of a Procedure.

    SID:010,5,ALSE1E,RW34R,SOKEN,OT,P,C,E   , ,   ,CF, ,DIA,OT,D, ,      ,3493,0132,3360,0100,+,02500,     ,13000, ,   ,    ,   ,OTHH,OT,P,A, , , , ;

    """
    def __init__(self, name: str):
        Procedure.__init__(self, name)

    def getRoute(self, airspace: Airspace):
        a = []
        for v in self.route.keys():
            fid = self.route[v].param(PROC_DATA.FIX_IDENT).strip()
            if len(fid) > 0:
                vid = self.route[v].param(PROC_DATA.ICAO_CODE) + ":" + self.route[v].param(PROC_DATA.FIX_IDENT)
                # logger.debug("Approach::getRoute: searching %s" % vid)
                vtxs = list(filter(lambda x: x.startswith(vid), airspace.vert_dict.keys()))
                if len(vtxs) == 1:
                    a.append(airspace.vert_dict[vtxs[0]])
                else:
                    logger.warning("SID::getRoute: vertex not found %s", vid)
        return a


class STAR(Procedure):
    """
    A Standard Terminal Arrival Route is a special instance of a Procedure.

    STAR:030,5,AFNA1E,RW34R,LOVAN,OB,E,A,E   , ,   ,TF, , , , , ,      ,    ,    ,    ,    ,-,08000,     ,     ,-,220,    ,   , , , , , , , , ;

    """
    def __init__(self, name: str):
        Procedure.__init__(self, name)

    def getRoute(self, airspace: Airspace):
        a = []
        for v in self.route.keys():
            fid = self.route[v].param(PROC_DATA.FIX_IDENT).strip()
            if len(fid) > 0:
                vid = self.route[v].param(PROC_DATA.ICAO_CODE) + ":" + self.route[v].param(PROC_DATA.FIX_IDENT)
                # logger.debug("Approach::getRoute: searching %s" % vid)
                vtxs = list(filter(lambda x: x.startswith(vid), airspace.vert_dict.keys()))
                if len(vtxs) == 1:
                    a.append(airspace.vert_dict[vtxs[0]])
                else:
                    logger.warning("SID::getRoute: vertex not found %s", vid)
        return a


class Approach(Procedure):
    """
    Approach procedure to runway.

    APPCH:030,D,D16L, ,MD16L,OT,P,C,E  M, ,   ,CF, ,DOH,OT,D, ,      ,3460,0056,1660,0063, ,00995,     ,     , ,   ,-300,   , , , , , ,0, ,S;

    """
    def __init__(self, name: str):
        Procedure.__init__(self, name)

    def getRoute(self, airspace: Airspace):
        interrupted = False
        a = []
        for v in self.route.keys():
            code = self.route[v].param(PROC_DATA.DESC_CODE)[0]
            if code == "E" and not interrupted:
                vid = self.route[v].param(PROC_DATA.ICAO_CODE) + ":" + self.route[v].param(PROC_DATA.FIX_IDENT)
                # logger.debug("Approach::getRoute: searching %s" % vid)
                vtxs = list(filter(lambda x: x.startswith(vid), airspace.vert_dict.keys()))
                if len(vtxs) == 1:
                    a.append(airspace.vert_dict[vtxs[0]])
                else:
                    logger.warning("Approach::getRoute: vertex not found %s", vid)
            else:
                if not interrupted:
                    logger.debug("Approach::getRoute: interrupted%s", "" if len(self.route[v].param(PROC_DATA.FIX_IDENT).strip()) == 0 else (" at %s " % self.route[v].param(PROC_DATA.FIX_IDENT)))
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


class Runway(Procedure):
    """
    A runway for starting a SID or terminating a STAR.

        0     1     2      3     4 5    6 7             8          9
    RWY:RW16L,     ,      ,00013, ,IDE ,3,   ;N25174597,E051363196,0000;

    """
    def __init__(self, name: str, airport: str):
        Procedure.__init__(self, name)
        self.airport = airport  ## Needed to create valid control point for runway
        self.runway = name
        self.point = None


    def add(self, line: ProcedureData):
        if self.point is not None:
            logger.warning("Runway::add: Cannot add to an already defined runway")
            return

        self.route[0] = line
        self.point = RestrictedControlledPoint(
            ident=line.params[0],
            region=self.airport[0:2],
            airport=self.airport,
            pointtype="RWY",
            lat=self.getLatitude(),
            lon=self.getLongitude()
        )
        self.setAltitude(float(self.route[0].params[3]))

    def getLatitude(self):
        latstr = self.route[0].params[7].split(";")[1]
        return ConvertDMSToDD(latstr[1:3], latstr[3:5], int(latstr[5:9])/100, latstr[0])

    def getLongitude(self):
        lonstr = self.route[0].params[8]
        return ConvertDMSToDD(lonstr[1:4], lonstr[4:6], int(lonstr[6:10])/100, lonstr[0])

    def setAltitude(self, alt):
        if len(self.point["geometry"]["coordinates"]) < 3:
            self.point["geometry"]["coordinates"].append(alt)
        else:
            self.point["geometry"]["coordinates"][2] = alt

    def getAltitude(self):
        return self.point["geometry"]["coordinates"][2]

    def getRunway(self):
        return self.point

    def getRoute(self):
        # logger.debug("Runway::getRoute: point %s" % self.point)
        return [self.point]


class CIFP:

    def __init__(self, icao: str):
        self.icao = icao
        self.procs = {
            "SID": {},
            "STAR": {},
            "APPCH": {},
            "RWY": {}
        }
        self.loadFromFile()

    def loadFromFile(self):
        """
        Loads Coded Instrument Flight Procedures

        :returns:   { description_of_the_return_value }
        :rtype:     { return_type_description }
        """
        cipf_filename = os.path.join(SYSTEM_DIRECTORY, "Resources", "default data", "CIFP", self.icao + ".dat")
        cifp_fp = open(cipf_filename, "r")
        line = cifp_fp.readline()
        prevline = None

        while line:
            cifpline = ProcedureData(line.strip())
            procty = cifpline.proc()
            procname = cifpline.name()

            if procty == "PRDAT":  # continuation of last line of current procedure
                if prevline is not None:
                    prevline.addData(cifpline)
                else:
                    logging.warning("Procedures::loadCIFP: received PRDAT but no procedure to add to")
            else:
                if procname not in self.procs[procty].keys():
                    if procty == "SID":
                        self.procs[procty][procname] = SID(procname)
                    elif procty == "STAR":
                        self.procs[procty][procname] = STAR(procname)
                    elif procty == "APPCH":
                        self.procs[procty][procname] = Approach(procname)
                    elif procty == "RWY":
                        self.procs[procty][procname] = Runway(procname, self.icao)
                    else:
                        logging.warning("Procedures::loadCIFP: invalid procedure %s", procty)
                if procname in self.procs[procty].keys():
                    self.procs[procty][procname].add(cifpline)
                else:
                    logging.warning("Procedures::loadCIFP: procedure not created %s", procty)

            prevline = cifpline
            line = cifp_fp.readline()

        ## Print result
        for procty in self.procs.keys():
            logging.debug("Procedures:: %s: %s" % (procty, self.procs[procty].keys()))


    def getRoute(self, procedure: Procedure, airspace: Airspace):
        return procedure.getRoute(airspace)
