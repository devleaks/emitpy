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
from ..utils import machToKmh, NAUTICAL_MILE, FT, toKmh

logger = logging.getLogger("Aircraft")


class ACPERF:
    icao = "icao"
    iata = "iata"
    takeoff_speed = "takeoff_speed"
    takeoff_distance = "takeoff_distance"
    takeoff_wtc = "takeoff_wtc"
    takeoff_recat = "takeoff_recat"
    takeoff_mtow = "takeoff_mtow"
    initial_climb_speed = "initial_climb_speed"
    initial_climb_vspeed = "initial_climb_vspeed"
    climbFL150_speed = "climbFL150_speed"
    climbFL150_vspeed = "climbFL150_vspeed"
    climbFL240_speed = "climbFL240_speed"
    climbFL240_vspeed = "climbFL240_vspeed"
    climbmach_mach = "climbmach_mach"
    climbmach_vspeed = "climbmach_vspeed"
    cruise_speed = "cruise_speed"
    cruise_mach = "cruise_mach"
    max_ceiling = "max_ceiling"
    cruise_range = "cruise_range"
    descentFL240_mach = "descentFL240_mach"
    descentFL240_vspeed = "descentFL240_vspeed"
    descentFL100_speed = "descentFL100_speed"
    descentFL100_vspeed = "descentFL100_vspeed"
    approach_speed = "approach_speed"
    approach_vspeed = "approach_vspeed"
    landing_speed = "landing_speed"
    landing_distance = "landing_distance"
    landing_apc = "landing_apc"


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
        self.perffile = None
        self.perfraw = None
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
                acperf.perfraw = jsondata[ac]
                acperf.toSI()
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
            if "cruise_range" in AircraftPerformance._DB_PERF[ac].perfraw:
                r = int(AircraftPerformance._DB_PERF[ac].perfraw["cruise_range"]) * NAUTICAL_MILE
                if r > reqrange:
                    rd = reqrange - r
                    if rd < rdiff:
                        rdiff = rd
                        best = ac
        return AircraftPerformance._DB_PERF[best]


    def loadPerformance(self):
        if self.perfraw is None:
            filename = os.path.join(DATA_DIR, AIRCRAFT_TYPE_DATABASE, self.typeId.upper()+".json")
            if os.path.exists(filename):
                with open(filename, "r") as file:
                    self.perfraw = json.load(file)
                    self.perffile = file
                logger.debug(":loadPerformance: loaded %d perfs for aircraft type %s" % (len(self.perfraw), self.typeId.upper()))
            else:  # fall back on aircraft performance category (A-F)
                logger.warning(":loadPerformance: file not found %s" % filename)
                filename = os.path.join(DATA_DIR, AIRCRAFT_TYPE_DATABASE, self.classId.upper()+".json")
                if os.path.exists(filename):
                    with open(filename, "r") as file:
                        self.perfraw = json.load(file)
                        self.perffile = file
                    logger.debug(":loadPerformance: loaded average %d perfs for aircraft class %s" % (len(self.perfraw), self.classId.upper()))
                else:
                    logger.warning(":loadPerformance: file not found %s" % filename)
                    filename = os.path.join(DATA_DIR, AIRCRAFT_TYPE_DATABASE, "STD.json")
                    if os.path.exists(filename):
                        with open(filename, "r") as file:
                            self.perfraw = json.load(file)
                            self.perffile = file
                        logger.debug(":loadPerformance: loaded %d standard perfs data for aircraft, ignoring model" % (len(self.perfraw)))
                    else:
                        logger.warning(":loadPerformance: average perfs file %s for aircraft not found" % (filename))
                        logger.warning(":loadPerformance: no performance data file for %s" % self.typeId.upper())
        self.toSI()

    """
    {
        "icao": "A321",
        "takeoff_speed": 145,
        "takeoff_distance": 2210,
        "takeoff_wtc": "M",
        "takeoff_recat": "Upper Medium",
        "takeoff_mtow": 83000,
        "initial_climb_speed": 175,
        "initial_climb_vspeed": 2500,
        "climbFL150_speed": 290,
        "climbFL150_vspeed": 2000,
        "climbFL240_speed": 290,
        "climbFL240_vspeed": 1800,
        "climbmach_mach": 0.78,
        "climbmach_vspeed": 1000,
        "cruise_speed": 450,
        "cruise_mach": 0.79,
        "max_ceiling": 410,
        "cruise_range": 2350,
        "descentFL240_mach": 0.78,
        "descentFL240_vspeed": 1000,
        "descentFL100_speed": 290,
        "descentFL100_vspeed": 2500,
        "approach_speed": 210,
        "approach_vspeed": 1500,
        "landing_speed": 141,
        "landing_distance": 1600,
        "landing_apc": "C",
        "iata": "321/32S"
    }
    """
    def toSI(self):
        if self.perfdata is None:
            self.perfdata = {}
            err = 0

            for name in ["initial_climb_vspeed", "climbFL150_vspeed", "climbFL240_vspeed", "climbmach_vspeed", "descentFL240_vspeed", "descentFL100_vspeed", "approach_vspeed"]:  # vspeed: ft/m -> m/s
                if name in self.perfraw and self.perfraw[name] != "no data":
                    self.perfdata[name] = self.perfraw[name] * FT / 60
                else:
                    logger.warning(":toSI: %s no value for: %s" % (self.name, name))
                    err = err + 1

            for name in ["takeoff_speed", "initial_climb_speed", "climbFL150_speed", "climbFL240_speed", "cruise_speed", "descentFL100_speed", "approach_speed", "landing_speed"]:  # speed: kn -> m/s
                if name in self.perfraw and self.perfraw[name] != "no data":
                    self.perfdata[name] = self.perfraw[name] * NAUTICAL_MILE / 3.600
                else:
                    logger.warning(":toSI: %s no value for: %s" % (self.name, name))
                    err = err + 1

            for name in ["climbmach_mach", "descentFL240_mach"]:  # speed: mach -> m/s
                if name in self.perfraw and self.perfraw[name] != "no data":
                    kmh = machToKmh(self.perfraw[name], 24000)
                    self.perfdata[name] = kmh / 3.6
                else:
                    logger.warning(":toSI: %s no value for: %s" % (self.name, name))
                    err = err + 1

            for name in ["cruise_mach"]:  # speed: mach -> m/s
                if name in self.perfraw and self.perfraw[name] != "no data":
                    kmh = machToKmh(self.perfraw[name], 30000)
                    self.perfdata[name] = kmh / 3.6
                else:
                    logger.warning(":toSI: %s no value for: %s" % (self.name, name))
                    err = err + 1

        # copy others verbatim
        for n in self.perfraw.keys():
            if n not in self.perfdata.keys():
                self.perfdata[n] = self.perfraw[n]

    def get(self, name: str):
        if name in self.perfraw.keys():
            return self.perfraw[name]
        else:
            logger.warning(":get: no value for: %s" % name)
        return None


    def getSI(self, name: str):
        if name in self.perfdata.keys():
            return self.perfdata[name]
        else:
            logger.warning(":getSI: no value for: %s" % name)
        return None


    def FLFor(self, reqrange: int):
        if reqrange < 300:
            return 200
        if reqrange < 500:
            return 240
        if reqrange < 1000:
            return 280
        return 340

    def perfs(self):
        for name in self.perfdata.keys():
            logger.debug(":perfs: %s %s %s" % (name, self.get(name), self.getSI(name)))

    #
    # Take-off helper functions
    #

    #
    # Climb helper functions
    #
    def climb(self, altstart, altend, vspeed, speed):

        t = (altend - altstart) / vspeed
        d = speed * t
        logger.debug(":climb: %s from %f to %f at %f m/s during %f, move %f at %f m/s" % (self.name, altstart, altend, vspeed, t, d, speed))
        return (t, d, altend)

    def initialClimb(self, altstart, safealt: int = 1500*FT):
        # Time to climb what is usually accepted as 1500ft AGL
        return self.climb(altstart, altstart + safealt, self.getSI(ACPERF.initial_climb_vspeed), self.getSI(ACPERF.initial_climb_speed))

    def climbToFL100(self, altstart):
        return self.climb(altstart, 10000*FT, self.getSI(ACPERF.climbFL150_vspeed), self.fl100Speed())

    def fl100Speed(self):
        maxfl100 = toKmh(250) / 3.6  # m/s
        return min(self.getSI(ACPERF.climbFL150_speed), maxfl100)

    def climbToFL150(self, altstart):
        return self.climb(altstart, 15000*FT, self.getSI(ACPERF.climbFL150_vspeed), self.getSI(ACPERF.climbFL150_speed))

    def climbToFL240(self, altstart):
        return self.climb(altstart, 24000*FT, self.getSI(ACPERF.climbFL240_vspeed), self.getSI(ACPERF.climbFL240_speed))

    def climbToCruise(self, altstart, altcruise):
        avgalt = (altstart + altcruise) / 2
        avgspd = machToKmh(self.get(ACPERF.climbmach_mach), avgalt) / 3.6  # m/s
        return self.climb(altstart, altcruise, self.getSI(ACPERF.climbmach_vspeed), avgspd)

    #
    # Descent helper functions
    #
    def descentToFL240(self, altcruise):
        altend = 24000*FT
        avgalt = (altcruise + altend) / 2
        avgspd = machToKmh(self.get(ACPERF.descentFL240_mach), avgalt) / 3.6  # m/s
        return self.climb(altcruise, altend, - self.getSI(ACPERF.descentFL240_vspeed), avgspd)

    def descentToFL100(self, altstart):
        return self.climb(altstart, 10000*FT, - self.getSI(ACPERF.descentFL100_vspeed), self.getSI(ACPERF.descentFL100_speed))

    def descentApproach(self, altstart, altend):
        return self.climb(altstart, altend, - self.getSI(ACPERF.approach_vspeed), self.getSI(ACPERF.approach_speed))

    def descentFinal(self, altstart, altend):
        return self.climb(altstart, altend, - self.getSI(ACPERF.approach_vspeed), self.getSI(ACPERF.landing_speed))

    #
    # Landing helper functions
    #



class Aircraft:
    """
    """
    def __init__(self, registration: str, actype: AircraftPerformance, operator: Company):
        self.registration = registration
        self.operator = operator
        self.actype = actype
        self.callsign = None
        self._position = None
        self._speed = 0
        self._vspeed = 0


    def setCallsign(self, callsign: str):
        self.callsign = callsign


    def setPosition(self, position):
        self._position = position

    def setSpeed(self, speed: float):
        self._speed = speed

    def setVSpeed(self, vspeed: float):
        self._vspeed = vspeed

    def position(self):
        return self._position

    def speed(self):
        return self._speed

    def vspeed(self):
        return self._vspeed
