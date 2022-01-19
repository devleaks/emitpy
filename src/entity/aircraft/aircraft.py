"""

"""
import os
import csv
import yaml
import logging

from ..business import Company
from ..constants import AIRCRAFT_TYPE_DATABASE
from ..parameters import DATA_DIR

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
        logger.debug("AircraftType::loadAll: loaded %d aircraft types" % len(AircraftType._DB))


    @staticmethod
    def find(icao: str):
        return AircraftType._DB[icao] if icao in AircraftType._DB else None



class AircraftPerformance(AircraftType):
    """
    """
    def __init__(self, orgId: str, classId: str, typeId: str, name: str):
        AircraftType.__init__(self, orgId, classId, typeId, name)
        self.perfdatafile = None
        self.perfdata = None


    def loadPerformance(self):
        if self.perfdata is None:
            filename = os.path.join(DATA_DIR, AIRCRAFT_TYPE_DATABASE, self.typeId.upper()+".yaml")
            if os.path.exists(filename):
                file = open(filename, "r")
                self.perfdata = yaml.safe_load(file)
                self.perfdatafile = file
                file.close()
                logger.debug("AircraftPerformance::loadPerformance: load %d perfs for %s" % (len(self.perfdata), self.typeId.upper()))
            else:  # fall back on aircraft performance category (A-F)
                logger.warning("AircraftPerformance::loadPerformance: file not found %s" % filename)
                filename = os.path.join(DATA_DIR, AIRCRAFT_TYPE_DATABASE, self.classId.upper()+".yaml")
                if os.path.exists(filename):
                    file = open(filename, "r")
                    self.perfdata = yaml.safe_load(file)
                    self.perfdatafile = file
                    file.close()
                    logger.debug("AircraftPerformance::loadPerformance: load %d perfs for %s" % (len(self.perfdata), self.typeId.upper()))
                else:
                    logger.warning("AircraftPerformance::loadPerformance: file not found %s" % filename)
                    logger.warning("AircraftPerformance::loadPerformance: no performance data file for %s" % self.typeId.upper())



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

