"""
Everything related to aircrafts, their codes, classes, performmances.
"""
import os
import csv
import json
import yaml
import logging
import operator
from math import inf

from ..business import Identity, Company
from ..constants import AIRCRAFT_TYPE_DATABASE
from ..parameters import DATA_DIR
from ..utils import machToKmh, NAUTICAL_MILE, FT, toKmh

logger = logging.getLogger("Aircraft")


class ACPERF:
    """
    List of aircraft performances. (Enum-like.)
    """
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


class AircraftType(Identity):
    """
    An AircraftType is a model of aircraft.
    - OrgId: Manufacturer
    - ClassId: Wake turbulence class
    - TypeId: ICAO model code
    - Name: Aircraft model name
    """

    _DB = {}
    _DB_EQUIVALENCE = {}

    def __init__(self, orgId: str, classId: str, typeId: str, name: str, data = None):
        Identity.__init__(self, orgId=orgId, classId=classId, typeId=typeId, name=name)
        self.rawdata = data

    @staticmethod
    def loadAll():
        """
        Loads all aircraft models from aircraft type data file.
        Current datafile contains the following CSV fields:
            Date Completed,Manufacturer,Model,Physical Class (Engine),# Engines,AAC,ADG,TDG,
            Approach Speed (Vref),Wingtip Configuration,Wingspan- ft,Length- ft,Tail Height- ft(@ OEW),
            Wheelbase- ft,Cockpit to Main Gear (CMG),MGW (Outer to Outer),MTOW,Max Ramp Max Taxi,
            Main Gear Config,ICAO Code,Wake Category,ATCT Weight Class,Years Manufactured,
            Note,Parking Area (WS x Length)- sf
        """
        filename = os.path.join(DATA_DIR, AIRCRAFT_TYPE_DATABASE, "aircraft-types.csv")
        file = open(filename, "r")
        csvdata = csv.DictReader(file)
        for row in csvdata:
            if row["ICAO Code"] != "tbd":
                AircraftType._DB[row["ICAO Code"]] = AircraftType(orgId=row["Manufacturer"], classId=row["Wake Category"], typeId=row["ICAO Code"], name=row["Model"], data=row)
        file.close()
        logger.debug(f":loadAll: loaded {len(AircraftType._DB)} aircraft types")

        # Aircraft equivalence patch(!)
        filename = os.path.join(DATA_DIR, AIRCRAFT_TYPE_DATABASE, "aircraft-equivalence.yaml")
        with open(filename, "r") as file:
            data = yaml.safe_load(file)
        AircraftType._DB_EQUIVALENCE = data
        logger.debug(f":loadAll: loaded {len(AircraftType._DB)} aircraft equivalences")


    @staticmethod
    def find(icao: str):
        """
        Returns aircraft type instance based on ICAO type code.

        :param      icao:  The icao
        :type       icao:  str
        """
        return AircraftType._DB[icao] if icao in AircraftType._DB else None


    def getInfo(self) -> dict:
        """
        Gets the information about an aircraft.
        """
        return {
            "actype-manufacturer": self.orgId,
            "actype": self.typeId,
            "acmodel": self.name
        }

    def getProp(self, name):
        """
        Gets a property from an aircraft.
        Returns None if property does not exist.
        Returns metric measures for imperial sizes.

        :param      name:  The name
        :type       name:  { type_description }
        """
        if self.rawdata:
            if name == "wingspan" and "Wingspan- ft" in self.rawdata:
                return float(self.rawdata["Wingspan- ft"]) / FT
            if name == "length" and "Length- ft" in self.rawdata:
                return float(self.rawdata["Length- ft"]) / FT
            return self.rawdata[name] if name in self.rawdata else None
        logger.warning(f":getProp: AircraftType {self.typeId} no raw data")
        return None

    def getClass(self) -> str:
        """
        Returns an aircraft type class for alternative or similar characteristic lookup.
        Current implementation returns letter A-F depending on aircraft size and weight.

        :returns:   The class.
        :rtype:     str
        """
        return self.classId


class AircraftPerformance(AircraftType):
    """
    The AircraftPerformance class augments the information available from the global aircraft database (AircraftType)
    with aircraft performance data necessary for the computation of its movements.
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
    _DB_PERF = {}

    def __init__(self, orgId: str, classId: str, typeId: str, name: str, data = None):
        AircraftType.__init__(self, orgId=orgId, classId=classId, typeId=typeId, name=name, data=data)
        self.perfraw = None
        self.gseprofile = None  # relative position of ground vehicle around the aircraft
        self.tarprofile = None  # relative scheduled time of services
        self.display_name = None

        self.perfdata = None  # computed
        self.available = False


    @staticmethod
    def loadAll():
        """
        Load all aircraft performance data files for all aircrafts where it is available.
        """
        filename = os.path.join(DATA_DIR, AIRCRAFT_TYPE_DATABASE, "aircraft-performances.json")
        file = open(filename, "r")
        jsondata = json.load(file)
        for ac in jsondata.keys():
            actype = AircraftType.find(ac)
            if actype is not None:
                acperf = AircraftPerformance(actype.orgId, actype.classId, actype.typeId, actype.name, actype.rawdata)
                acperf.display_name = acperf.orgId + " " + acperf.name
                acperf.perfraw = jsondata[ac]
                if acperf.check_availability():  # sets but also returns availability
                    acperf.toSI()
                AircraftPerformance._DB_PERF[ac] = acperf
            else:
                logger.warning(f":loadAll: AircraftType {ac} not found")
        file.close()
        cnt = len(list(filter(lambda a: a.available, AircraftPerformance._DB_PERF.values())))
        logger.debug(f":loadAll: loaded {len(AircraftPerformance._DB_PERF)} aircraft types with their performances, {cnt} available")
        logger.debug(f":loadAll: {list(map(lambda f: (f.typeId, f.getIata()), AircraftPerformance._DB_PERF.values()))}")


    @staticmethod
    def find(icao: str):
        """
        Returns AircraftPerformance type instance based on ICAO type code.

        :param      icao:  The icao
        :type       icao:  str
        """
        return AircraftPerformance._DB_PERF[icao] if icao in AircraftPerformance._DB_PERF else None


    @staticmethod
    def findAircraftForRange(reqrange: int, pax: int = 0, cargo: int = 0):
        """
        Find an aircraft suitable for the requested flight range.

        :param      reqrange:  The reqrange
        :type       reqrange:  int
        :param      pax:       The pax load information. Currently ignored, for future use.
        :type       pax:       int
        :param      load:      The cargo load information. Currently ignored, for future use.
        :type       load:      int
        """
        rdiff = inf
        best = None
        for ac in AircraftPerformance._DB_PERF.keys():
            if AircraftPerformance._DB_PERF[ac].available  and ("cruise_range" in AircraftPerformance._DB_PERF[ac].perfraw):
                r = int(AircraftPerformance._DB_PERF[ac].perfraw["cruise_range"]) * NAUTICAL_MILE  # km
                if r > reqrange:
                    rd = r - reqrange
                    # logger.debug(":findAircraft: can use %s: %f (%f)" % (ac, r, rd))
                    if rd < rdiff:
                        rdiff = rd
                        best = ac
                        # logger.debug(":findAircraft: best %f" % rdiff)
        return AircraftPerformance._DB_PERF[best]


    @staticmethod
    def getEquivalence(ac):
        """
        Attempt to guess an aircraft code equivalence.
        Example: B777 ->["777", "B77L", "77L"...]
        The aircraft equivalence should be set as an aircraft performance data.

        :param      ac:   { parameter_description }
        :type       ac:   { type_description }
        """
        for k, v in AircraftType._DB_EQUIVALENCE.items():
            if ac in v:
                return k
        logger.warning(f":getEquivalence: no equivalence for {ac}")
        return None


    @staticmethod
    def findAircraftByType(actype: str, acsubtype: str):
        """
        Returns existing AircraftPerformance aircraft or None if aircraft cannot be found.

        :param      actype:     The actype, loosely connected to ICAO type code
        :type       actype:     str
        :param      acsubtype:  The acsubtype, loosely connected to AITA type code
        :type       acsubtype:  str

        :returns:   The aircraft performance.
        :rtype:     AircraftPerformance
        """
        if actype in AircraftPerformance._DB_PERF.keys():
            logger.debug(f":findAircraftByType: found type {actype}")
            return actype
        if acsubtype in AircraftPerformance._DB_PERF.keys():
            logger.debug(f":findAircraftByType: found sub type {acsubtype}")
            return acsubtype
        eq = AircraftPerformance.getEquivalence(actype)
        if eq is not None:
            logger.debug(f":findAircraftByType: found equivalence {eq} for type {actype}")
            return eq
        eq = AircraftPerformance.getEquivalence(acsubtype)
        if eq is not None:
            logger.debug(f":findAircraftByType: found equivalence {eq} for subtype {acsubtype}")
            return eq
        logger.warning(f":findAircraftByType: no aircraft for {actype}, {acsubtype}")
        return None


    @staticmethod
    def getCombo():
        """
        Gets a list of pairs (code, description) for all aircafts in the AircraftPerformance database.
        """
        l = filter(lambda a: a.available, AircraftPerformance._DB_PERF.values())
        a = [(a.typeId, a.display_name) for a in sorted(l, key=operator.attrgetter('display_name'))]
        return a


    def getIata(self):
        """
        Gets the IATA code of an aircraft type if available.
        """
        iata = self.perfraw["iata"] if ("iata" in self.perfraw and self.perfraw["iata"] is not None and self.perfraw["iata"] != "nodata") else None
        return str(iata).split("/") if iata else []


    def load(self):
        """
        Loads additional aircraft performance or characteristic data
        necessary for the application.
        It loads Ground Support Vehicle Profile (how GSE vehicle arrange around the aircraft on the apron).
        It also loads Turnaround Profile, a typical service schedule pattern for arrival or departure service scheduling.
        """
        status = self.loadPerformance()

        if not status[0]:
            return status

        status = self.loadTurnaroundProfile()
        if not status[0]:
            return status

        status = self.loadGSEProfile()
        if not status[0]:
            return status

        return (True, f"AircraftPerformance loaded ({self.typeId})")

    def loadFromFile(self, extension: str):
        """
        Loads the file self.filename and store its content in self.data.
        Based on the file extention, a proper loader is selected (text, json, yaml, or csv).

        :param      extension:  The extension
        :type       extension:  str
        """
        data = None
        filename = os.path.join(DATA_DIR, AIRCRAFT_TYPE_DATABASE, self.typeId.upper()+extension)
        if os.path.exists(filename):
            with open(filename, "r") as file:
                if filename[-5:] == ".yaml":
                    data = yaml.safe_load(file)
                else:  # JSON or GeoJSON
                    data = json.load(file)
            logger.debug(f":loadFromFile: loaded {filename} for aircraft type {self.typeId.upper()}")
        else:  # fall back on aircraft performance category (A-F)
            logger.warning(f":loadFromFile: file not found {filename}")
            filename = os.path.join(DATA_DIR, AIRCRAFT_TYPE_DATABASE, self.classId.upper()+extension)
            if os.path.exists(filename):
                with open(filename, "r") as file:
                    if filename[-5:] == ".yaml":
                        data = yaml.safe_load(file)
                    else:  # JSON or GeoJSON
                        data = json.load(file)
                logger.debug(f":loadFromFile: loaded class {filename} data for aircraft class {self.classId.upper()}")
            else:
                logger.warning(f":loadFromFile: file not found {filename}")
                filename = os.path.join(DATA_DIR, AIRCRAFT_TYPE_DATABASE, "STD" + extension)
                if os.path.exists(filename):
                    with open(filename, "r") as file:
                        if filename[-5:] == ".yaml":
                            data = yaml.safe_load(file)
                        else:  # JSON or GeoJSON
                            data = json.load(file)
                    logger.debug(f":loadFromFile: loaded {filename} standard data for aircraft, ignoring model")
                else:
                    logger.warning(f":loadFromFile: standard data file {filename} for aircraft not found")
                    logger.warning(f":loadFromFile: no data file for {self.typeId.upper()}")
        return data


    def loadPerformance(self):
        """
        Loads a performance data file for a single aircraft type.
        """
        if self.perfraw is None:
            data = self.loadFromFile(".json")
            if data is not None:
                self.perfraw = data
                if self.check_availability():
                    self.toSI()
            else:
                logger.warning(f":loadPerformance: no performance data file for {self.typeId.upper()}")
        return [True, "AircraftPerformance::loadPerformance: loaded"]


    def loadTurnaroundProfile(self):
        """
        Loads a turnaround profile data file for a single aircraft type.
        """
        if self.tarprofile is None:
            data = self.loadFromFile("-tarpro.yaml")
            if data is not None:
                self.tarprofile = data
            else:
                logger.warning(f":loadTurnaroundProfile: no turnaround profile data file for {self.typeId.upper()}")
        return [True, "AircraftPerformance::loadTurnaroundProfile: not implemented"]


    def loadGSEProfile(self):
        """
        Loads a ground support vehicle arrangement data file for a single aircraft type.
        """
        data = self.loadFromFile("-gsepro.yaml")
        if data is not None:
            self.gseprofile = data
        else:
            logger.warning(f":loadGSEProfile: no GSE profile data file for {self.typeId.upper()}")
        return [True, "AircraftPerformance::loadGSEProfile: not implemented"]


    def check_availability(self):
        """
        Check whether all perfomance data is available for this aircraft type.
        If not, the aircraft cannot be used in the application (insufficient data available).
        """
        max_ceiling = self.get("max_ceiling")  # this is a FL
        if max_ceiling is None:
            logger.warning(f":check_availability: no max ceiling for: {self.typeId}")
            return False

        param_list = ["takeoff_distance", "takeoff_speed", "initial_climb_speed", "initial_climb_vspeed"]
        param_list = param_list + ["cruise_speed", "cruise_range", "approach_speed", "approach_vspeed", "landing_speed", "landing_distance"]

        param_list = param_list + ["climbFL150_speed", "climbFL150_vspeed"]
        if max_ceiling > 150:
            param_list = param_list + ["climbFL240_speed", "climbFL240_vspeed"]
            param_list = param_list + ["descentFL100_speed", "descentFL100_vspeed"]
        if max_ceiling > 240:
            param_list = param_list + ["climbmach_mach", "climbmach_vspeed"]
            param_list = param_list + ["descentFL240_mach", "descentFL240_vspeed"]

        for name in param_list:
            if name not in self.perfraw or self.perfraw[name] == "no data":
                logger.warning(f":check_availability: no {name} for: {self.typeId}, rejecting")
                return False
        self.available = True
        # logger.warning(f":check_availability: {self.typeId} is ok")
        return True


    def toSI(self):
        """
        Converts numeric performance data to Système International.
        Uses meters, seconds, meter per second, hecto-pascal, etc.
        """
        if self.perfdata is None:
            self.perfdata = {}
            err = 0

            for name in ["initial_climb_vspeed", "climbFL150_vspeed", "climbFL240_vspeed", "climbmach_vspeed", "descentFL240_vspeed", "descentFL100_vspeed", "approach_vspeed"]:  # vspeed: ft/m -> m/s
                if name in self.perfraw and self.perfraw[name] != "no data":
                    self.perfdata[name] = self.perfraw[name] * FT / 60
                else:
                    logger.warning(f":toSI: {self.name} no value for: {name}")
                    err = err + 1

            for name in ["takeoff_speed", "initial_climb_speed", "climbFL150_speed", "climbFL240_speed", "cruise_speed", "descentFL100_speed", "approach_speed", "landing_speed"]:  # speed: kn -> m/s
                if name in self.perfraw and self.perfraw[name] != "no data":
                    self.perfdata[name] = self.perfraw[name] * NAUTICAL_MILE / 3.600
                else:
                    logger.warning(f":toSI: {self.name} no value for: {name}")
                    err = err + 1

            for name in ["climbmach_mach", "descentFL240_mach"]:  # speed: mach -> m/s
                if name in self.perfraw and self.perfraw[name] != "no data":
                    kmh = machToKmh(self.perfraw[name], 24000)
                    self.perfdata[name] = kmh / 3.6
                else:
                    logger.warning(f":toSI: {self.name} no value for: {name}")
                    err = err + 1

            for name in ["cruise_mach"]:  # speed: mach -> m/s
                if name in self.perfraw and self.perfraw[name] != "no data":
                    kmh = machToKmh(self.perfraw[name], 30000)
                    self.perfdata[name] = kmh / 3.6
                else:
                    logger.warning(f":toSI: {self.name} no value for: {name}")
                    err = err + 1

        # copy others verbatim
        for n in self.perfraw.keys():
            if n not in self.perfdata.keys():
                if self.perfraw[n] != "no data":
                    self.perfdata[n] = self.perfraw[n]
                else:
                    logger.warning(f":toSI: {self.name} no value for: {n}")


    def get(self, name: str):
        """
        Get performance raw value

        :param      name:  The name
        :type       name:  str
        """
        if name in self.perfraw.keys():
            return self.perfraw[name]
        else:
            logger.warning(f":get: no value for: {name}")
        return None


    def getSI(self, name: str):
        """
        Get performance value in SI unit system.

        :param      name:  The name
        :type       name:  str
        """
        if name in self.perfdata.keys():
            return self.perfdata[name]
        else:
            logger.warning(f":getSI: no value for: {name}")
        return None


    def FLFor(self, reqrange: int):
        """
        Estimates a flight level for supplied range.
        (No need to go FL340 for a 200km flight. Not a formal computation, just a reasonable suggestion.)
        The aircraft type max_ceiling is taken into consideration.

        :param      reqrange:  The reqrange
        :type       reqrange:  int
        """
        max_ceiling = self.get("max_ceiling")
        if max_ceiling is None:
            logger.warning(f":FLFor: no max ceiling for: {self.typeId}, assuming max ceiling is FL300")
            max_ceiling = 300
        # Set Flight Level for given flight range in km.
        if reqrange < 300:
            return min(200, max_ceiling)
        if reqrange < 500:
            return min(240, max_ceiling)
        if reqrange < 1000:
            return min(280, max_ceiling)
        return min(340, max_ceiling)


    def perfs(self):
        """
        Convenience function to print all aircraft available performance data.
        """
        for name in self.perfdata.keys():
            logger.debug(f":perfs: {name} {self.get(name)} {self.getSI(name)}")

    #
    # Take-off helper functions
    #

    #
    # Climb helper functions
    #
    def climb(self, altstart, altend, vspeed, speed):
        """
        Compute distance necessary to climb or descent (negative vspeed) from altstart altitude
        to endalt altitude, moving at vspeed vertical speed at speed.
        All distance are in meters, all speeds are in meters per second.
        """
        t = (altend - altstart) / vspeed
        d = speed * t
        # logger.debug(":climb: %s from %f to %f at %f m/s during %f, move %f at %f m/s" % (self.name, altstart, altend, vspeed, t, d, speed))
        return (t, d, altend)

    def initialClimb(self, altstart, safealt: int = 1500*FT):
        """
        Alias to clib function for initialClimb speed and vspeed.

        :param      altstart:  The altstart
        :type       altstart:  { type_description }
        :param      safealt:   The safealt
        :type       safealt:   int
        """
        # Time to climb what is usually accepted as 1500ft AGL
        return self.climb(altstart, altstart + safealt, self.getSI(ACPERF.initial_climb_vspeed), self.getSI(ACPERF.initial_climb_speed))

    def climbToFL100(self, altstart):
        """
        Alias to clib function for initialClimb speed and vspeed.

        :param      altstart:  The altstart
        :type       altstart:  { type_description }
        :param      safealt:   The safealt
        :type       safealt:   int
        """
        # Time to climb what is usually accepted as 1500ft AGL
        return self.climb(altstart, 10000*FT, self.getSI(ACPERF.climbFL150_vspeed), self.fl100Speed())

    def fl100Speed(self):
        """
        Alias to clib function for FL100 speed and vspeed.

        :param      altstart:  The altstart
        :type       altstart:  { type_description }
        :param      safealt:   The safealt
        :type       safealt:   int
        """
        # Time to climb what is usually accepted as 1500ft AGL
        maxfl100 = toKmh(250) / 3.6  # m/s
        return min(self.getSI(ACPERF.climbFL150_speed), maxfl100)

    def climbToFL150(self, altstart):
        """
        Alias to clib function for FL150 speed and vspeed.

        :param      altstart:  The altstart
        :type       altstart:  { type_description }
        :param      safealt:   The safealt
        :type       safealt:   int
        """
        # Time to climb what is usually accepted as 1500ft AGL
        return self.climb(altstart, 15000*FT, self.getSI(ACPERF.climbFL150_vspeed), self.getSI(ACPERF.climbFL150_speed))

    def climbToFL240(self, altstart):
        """
        Alias to clib function for FL240 speed and vspeed.

        :param      altstart:  The altstart
        :type       altstart:  { type_description }
        :param      safealt:   The safealt
        :type       safealt:   int
        """
        # Time to climb what is usually accepted as 1500ft AGL
        return self.climb(altstart, 24000*FT, self.getSI(ACPERF.climbFL240_vspeed), self.getSI(ACPERF.climbFL240_speed))

    def climbToCruise(self, altstart, altcruise):
        """
        Alias to clib function for cruise speed and vspeed.

        :param      altstart:  The altstart
        :type       altstart:  { type_description }
        :param      safealt:   The safealt
        :type       safealt:   int
        """
        # Time to climb what is usually accepted as 1500ft AGL
        avgalt = (altstart + altcruise) / 2
        avgspd = machToKmh(self.get(ACPERF.climbmach_mach), avgalt) / 3.6  # m/s
        return self.climb(altstart, altcruise, self.getSI(ACPERF.climbmach_vspeed), avgspd)

    #
    # Descent helper functions
    #
    # @todo: Should catch absence of descent speed
    #
    def descentToFL240(self, altcruise):
        """
        Alias to clib function to descent to FL240 speed and vspeed.

        :param      altstart:  The altstart
        :type       altstart:  { type_description }
        :param      safealt:   The safealt
        :type       safealt:   int
        """
        altend = 24000*FT
        avgalt = (altcruise + altend) / 2
        avgspd = machToKmh(self.get(ACPERF.descentFL240_mach), avgalt) / 3.6  # m/s
        return self.climb(altcruise, altend, - self.getSI(ACPERF.descentFL240_vspeed), avgspd)

    def descentToFL100(self, altstart):
        """
        Alias to clib function to descent to FL100 speed and vspeed.

        :param      altstart:  The altstart
        :type       altstart:  { type_description }
        :param      safealt:   The safealt
        :type       safealt:   int
        """
        return self.climb(altstart, 10000*FT, - self.getSI(ACPERF.descentFL100_vspeed), self.getSI(ACPERF.descentFL100_speed))

    def descentApproach(self, altstart, altend):
        """
        Alias to clib function to descent to approach speed and vspeed.

        :param      altstart:  The altstart
        :type       altstart:  { type_description }
        :param      safealt:   The safealt
        :type       safealt:   int
        """
        return self.climb(altstart, altend, - self.getSI(ACPERF.approach_vspeed), self.getSI(ACPERF.approach_speed))

    def descentFinal(self, altstart, altend):
        """
        Alias to clib function to descent to final speed and vspeed.

        :param      altstart:  The altstart
        :type       altstart:  { type_description }
        :param      safealt:   The safealt
        :type       safealt:   int
        """
        return self.climb(altstart, altend, - self.getSI(ACPERF.approach_vspeed), self.getSI(ACPERF.landing_speed))

    #
    # Landing helper functions
    #



class Aircraft:
    """
    An aircraft servicing an airline route.
    """
    def __init__(self, registration: str, icao24: str, actype: AircraftPerformance, operator: Company):
        """
        An aircraft servicing a flight.

        """
        self.registration = registration
        self.icao24 = icao24  # 6 hexadecimal digit string, ADS-B address
        self.operator = operator
        self.actype = actype
        self.callsign = None

    def setCallsign(self, callsign: str):
        """
        Sets the callsign for this aircraft.

        :param      callsign:  The callsign
        :type       callsign:  str
        """
        self.callsign = callsign

    def setICAO24(self, icao24: str):
        """
        Sets the icao 24 bit address of the aicraft transponder.

        :param      icao24:  The icao 24
        :type       icao24:  str
        """
        self.icao24 = icao24

    def getInfo(self) -> dict:
        """
        Gets information about this aircraft. Recurse to aircraft details (aircraft type, operator, etc).
        """
        return {
            "actype": self.actype.getInfo(),
            "operator": self.operator.getInfo(),
            "acreg": self.registration,
            "callsign": self.callsign,
            "icao24": self.icao24
        }