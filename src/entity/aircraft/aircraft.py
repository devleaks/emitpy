"""

"""
import os
import csv
import json
import logging
from math import inf

from ..business import Company
from ..constants import AIRCRAFT_TYPE_DATABASE
from ..parameters import DATA_DIR
from ..utils import NAUTICAL_MILE

logger = logging.getLogger("Aircraft")


class AircraftType:
    """
    """

    _DB = {}

    def __init__(self, orgId: str, classId: str, typeId: str, name: str):
        self.orgId = orgId          # Manufacturer
        self.classId = classId      # Aircraft
        self.typeId = typeId        # ICAO aircraft model
        self.name = name            # display name

    @staticmethod
    def loadAll():
        """
        "Date Completed","Manufacturer","Model","Physical Class (Engine)","# Engines","AAC","ADG","TDG",
        "Approach Speed (Vref)","Wingtip Configuration","Wingspan- ft","Length- ft","Tail Height- ft(@ OEW)",
        "Wheelbase- ft","Cockpit to Main Gear (CMG)","MGW (Outer to Outer)","MTOW","Max Ramp Max Taxi",
        "Main Gear Config","ICAO Code","Wake Category","ATCT Weight Class","Years Manufactured",
        "Note","Parking Area (WS x Length)- sf"
        """
        filename = os.path.join(DATA_DIR, AIRCRAFT_TYPE_DATABASE, "aircraft-types.csv")
        file = open(filename, "r")
        csvdata = csv.DictReader(file)
        for row in csvdata:
            if row["ICAO Code"] != "tbd":
                AircraftType._DB[row["ICAO Code"]] = AircraftType(orgId=row["Manufacturer"], classId=row["Wake Category"], typeId=row["ICAO Code"], name=row["Model"])
        file.close()
        logger.debug(":loadAll: loaded %d aircraft types" % len(AircraftType._DB))


    @staticmethod
    def find(icao: str):
        return AircraftType._DB[icao] if icao in AircraftType._DB else None


class AircraftPerformance(AircraftType):
    """
    """
    _DB_PERF = {}

    def __init__(self, orgId: str, classId: str, typeId: str, name: str):
        AircraftType.__init__(self, orgId, classId, typeId, name)
        self.perfdatafile = None
        self.perfdata = None


    @staticmethod
    def loadAll():
        """
        "Date Completed","Manufacturer","Model","Physical Class (Engine)","# Engines","AAC","ADG","TDG",
        "Approach Speed (Vref)","Wingtip Configuration","Wingspan- ft","Length- ft","Tail Height- ft(@ OEW)",
        "Wheelbase- ft","Cockpit to Main Gear (CMG)","MGW (Outer to Outer)","MTOW","Max Ramp Max Taxi",
        "Main Gear Config","ICAO Code","Wake Category","ATCT Weight Class","Years Manufactured",
        "Note","Parking Area (WS x Length)- sf"
        """
        filename = os.path.join(DATA_DIR, AIRCRAFT_TYPE_DATABASE, "aircraft-performances.json")
        file = open(filename, "r")
        jsondata = json.load(file)
        for ac in jsondata.keys():
            actype = AircraftType.find(ac)
            if actype is not None:
                acperf = AircraftPerformance(actype.orgId, actype.classId, actype.typeId, actype.name)
                acperf.perfdata = jsondata[ac]
                AircraftPerformance._DB_PERF[ac] = acperf
            else:
                logger.warning(":loadAll: AircraftType %s not found" % ac)
        file.close()
        logger.debug(":loadAll: loaded %d aircraft types with their performances" % len(AircraftPerformance._DB_PERF))


    @staticmethod
    def find(icao: str):
        return AircraftPerformance._DB_PERF[icao] if icao in AircraftPerformance._DB_PERF else None


    @staticmethod
    def findAircraft(reqrange: int, pax: int = 0, load: int = 0):
        rdiff = inf
        best = None
        for ac in AircraftPerformance._DB_PERF.keys():
            if "cruise_range" in AircraftPerformance._DB_PERF[ac].perfdata:
                r = int(AircraftPerformance._DB_PERF[ac].perfdata["cruise_range"]) * NAUTICAL_MILE
                if r > reqrange:
                    rd = reqrange - r
                    if rd < rdiff:
                        rdiff = rd
                        best = ac
        return AircraftPerformance._DB_PERF[best]


    def loadPerformance(self):
        if self.perfdata is None:
            filename = os.path.join(DATA_DIR, AIRCRAFT_TYPE_DATABASE, self.typeId.upper()+".json")
            if os.path.exists(filename):
                file = open(filename, "r")
                self.perfdata = json.load(file)
                self.perfdatafile = file
                file.close()
                logger.debug(":loadPerformance: loaded %d perfs for aircraft type %s" % (len(self.perfdata), self.typeId.upper()))
            else:  # fall back on aircraft performance category (A-F)
                logger.warning(":loadPerformance: file not found %s" % filename)
                filename = os.path.join(DATA_DIR, AIRCRAFT_TYPE_DATABASE, self.classId.upper()+".json")
                if os.path.exists(filename):
                    file = open(filename, "r")
                    self.perfdata = json.load(file)
                    self.perfdatafile = file
                    file.close()
                    logger.debug(":loadPerformance: loaded average %d perfs for aircraft class %s" % (len(self.perfdata), self.classId.upper()))
                else:
                    logger.warning(":loadPerformance: file not found %s" % filename)
                    filename = os.path.join(DATA_DIR, AIRCRAFT_TYPE_DATABASE, "STD.json")
                    if os.path.exists(filename):
                        file = open(filename, "r")
                        self.perfdata = json.load(file)
                        self.perfdatafile = file
                        file.close()
                        logger.debug(":loadPerformance: loaded %d standard perfs data for aircraft, ignoring model" % (len(self.perfdata)))
                    else:
                        logger.warning(":loadPerformance: average perfs file %s for aircraft not found" % (filename))
                        logger.warning(":loadPerformance: no performance data file for %s" % self.typeId.upper())



class Aircraft:
    """
    """
    def __init__(self, registration: str, actype: AircraftPerformance, operator: Company):
        self.registration = registration
        self.operator = operator
        self.actype = actype
        self.callsign = None


    def setCallsign(self, callsign: str):
        self.callsign = callsign

