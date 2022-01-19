"""
A Flight Route is an array of ProcedurePoint.
A ProcedurePoint is either a waypoint or just a coordinate with mandatory properties.
"""
import os
import logging

from ..parameters import DATA_DIR

SYSTEM_DIRECTORY = os.path.join(DATA_DIR, "x-plane")

logger = logging.getLogger("Airport")


class ProcedureData:
    # CIFP line for this airport
    def __init__(self, line):
        self.procedure = None
        self.params = []
        a = line.split(":")
        if len(a) == 0:
            logging.debug("ProcedureData::__init__: invalid line '%s'", line)
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

    def seq(self):
        return int(self.params[0])

    def rwy(self):
        return int(self.params[3])

    def content(self):
        return self.params.join(",")


class Procedure:
    """
    A Procedure is a named array of ProcedureData
    """
    def __init__(self, name: str):
        self.name = name
        self.route = []

    def add(self, line: ProcedureData):
        self.route.append(line)


class SID(Procedure):
    """
    A Standard Instrument Departure is a special instance of a Procedure.
    """
    def __init__(self, name: str):
        Procedure.__init__(self, name)


class STAR(Procedure):
    """
    A Standard Terminal Arrival Route is a special instance of a Procedure.
    """
    def __init__(self, name: str):
        Procedure.__init__(self, name)


class Approach(Procedure):
    """
    A transition from a START to a final fix.
    """
    def __init__(self, name: str):
        Procedure.__init__(self, name)


class Runway(Procedure):
    """
    A runway for starting a SID or terminating a STAR.
    """
    def __init__(self, name: str):
        Procedure.__init__(self, name)


class Procedures:

    def __init__(self, icao: str):
        self.icao = icao
        self.sids = {}
        self.stars = {}
        self.appchs = {}
        self.runways = {}
        self.loadFromFile()

    def loadFromFile(self):
        """
        Loads Coded Instrument Flight Procedures

        :returns:   { description_of_the_return_value }
        :rtype:     { return_type_description }
        """
        currproc = None

        cipf_filename = os.path.join(SYSTEM_DIRECTORY, "Resources", "default data", "CIFP", self.icao + ".dat")
        cifp_fp = open(cipf_filename, "r")
        line = cifp_fp.readline()

        while line:
            cifpline = ProcedureData(line.strip())
            procty = cifpline.proc()
            procname = cifpline.name()

            if procty == "PRDAT":  # continuation of last line of current procedure
                if currproc is not None:
                    currproc.add(cifpline)
                else:
                    logging.warning("Procedures::loadCIFP: received PRDAT but no current procedure")
            else:
                if (currproc is None) or ((type(currproc).__name__ != cifpline.proc()) or (type(currproc).__name__ != cifpline.name())):  # new proc
                    currproc = None
                    if procty == "SID":
                        currproc = SID(procname)
                        self.sids[procname] = currproc
                    elif procty == "STAR":
                        currproc = STAR(procname)
                        self.stars[procname] = currproc
                    elif procty == "APPCH":
                        currproc = Approach(procname)
                        self.appchs[procname] = currproc
                    elif procty == "RWY":
                        currproc = Runway(procname)
                        self.runways[procname] = currproc
                    else:
                        logging.warning("Procedures::loadCIFP: invalid procedure %s", procty)

                if currproc is not None:
                    currproc.add(cifpline)
                else:
                    logging.warning("ProceduresloadCIFP: no procedure to add to")

            line = cifp_fp.readline()

        logging.debug("Procedures:: SID: %s", self.sids.keys())
        logging.debug("Procedures:: STAR: %s", self.stars.keys())
        logging.debug("Procedures:: Approaches: %s", self.appchs.keys())
        logging.debug("Procedures:: Runways: %s", self.runways.keys())
