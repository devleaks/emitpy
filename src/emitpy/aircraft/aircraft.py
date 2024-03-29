"""
Everything related to aircrafts, their codes, classes, performmances.
"""

from enum import Enum
import sys
import logging
import operator
import os
import json
from math import inf
from typing import Tuple

from importlib_resources import files

# import pint
# pylint: disable=W0611
import csv
import yaml

# from openap import WRAP

from emitpy.parameters import HOME_DIR, DATA_DIR
from emitpy.business import Identity, Company
from emitpy.constants import AIRCRAFT_TYPE_DATABASE, REDIS_DATABASE, REDIS_PREFIX, REDIS_DB
from emitpy.constants import LOW_ALT_MAX_SPEED, LOW_ALT_ALT_FT, FINAL_APPROACH_FIX_ALT_M, INITIAL_CLIMB_SAFE_ALT_M
from emitpy.utils import convert, key_path, rejson, show_path


logger = logging.getLogger("Aircraft")

sys.path.append(HOME_DIR)

# ureg = pint.UnitRegistry()

_STD_CLASS = "C"


class ACPERF:
    """Aircraft performance data list.

    [description]

    Attributes:
        icao: Aircraft ICOA type designator
        iata: Aircraft IATA type designator
        takeoff_speed: Take off speed in m/s
        takeoff_distance: Average take-off distance on dry ground.
        takeoff_wtc: Take-off wake turbulance code.
        takeoff_recat: [description]
        takeoff_mtow: Maximum take-off weight
        initial_climb_speed: Speed in m/s immediately after take off
        initial_climb_vspeed: Vertical speed in ft/min (or m/s?) immediately after take off
        climbFL150_speed: Average speed to FL150
        climbFL150_vspeed: Average vertical speed in ft/min to FL150
        climbFL240_speed: Average speed to FL240
        climbFL240_vspeed: Average vertical speed in ft/min to FL240
        climbmach_mach: Average speed in mach number when climbing above FL240
        climbmach_vspeed: Average vertical speed in ft/min above FL240
        cruise_speed: Cruise speed
        cruise_mach: Cruise speed (mach number)
        max_ceiling: Maximum altitude for aircraft
        cruise_range: Cruise range in NM
        descentFL240_mach: [description]
        descentFL240_vspeed: [description]
        descentFL100_speed: [description]
        descentFL100_vspeed: [description]
        approach_speed: [description]
        approach_vspeed: [description]
        landing_speed: Average landing speed
        landing_distance: Average landing distance on dry ground
        landing_apc: [description]
        length: Aircraft length
        wingspan: Aircraft wingspan
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
    length = "length"
    wingspan = "wingspan"


class SPEED_RANGE(Enum):
    SLOW = 0
    FL150 = 1
    FL240 = 2
    FAST = 3


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

    def __init__(self, orgId: str, classId: str, typeId: str, name: str, data=None):
        """Create an aircraft type identifier

        [description]

        Args:
            orgId (str): Manufacturer
            classId (str): Type of aircraft
            typeId (str): ICAO aircraft type designator
            name (str): Aicraft model name like "Airbus A321-NX"
            data ([type]): Additional dictionary of accessory data (default: `None`)
        """
        Identity.__init__(self, orgId=orgId, classId=classId, typeId=typeId, name=name)
        self.iata = None
        self.rawdata = data
        self._ac_class = None

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
        ac = files("data.aircraft_types").joinpath("aircraft-types.json").read_text()
        data = json.loads(ac)
        for row in data:
            if row["ICAO Code"] != "tbd":
                AircraftType._DB[row["ICAO Code"]] = AircraftType(
                    orgId=row["Manufacturer"], classId=row["Wake Category"], typeId=row["ICAO Code"], name=row["Model"], data=row
                )
                AircraftType._DB[row["ICAO Code"]].setClass()
        logger.debug(f"loaded {show_path(files('data.aircraft_types').joinpath('aircraft-types.json'))}")
        logger.debug(f"loaded {len(AircraftType._DB)} aircraft types")
        AircraftType.loadAircraftEquivalences()

    @staticmethod
    def loadAircraftEquivalences():
        """
        Loads aircraft type equivalences. Be aware ICAO aircraft type name often
        does not discriminate from models: Ex. ICAO A350, IATA 350, 359, 358, 35K...
        While performances parameters are VERY different from version to version,
        for this simulation of tracks it will be accepted as good enough.
        If possible we work with detailed IATA model/submodel, if not ICAO model is OK.
        :param      icao:  The icao
        :type       icao:  str
        """
        ae = files("data.aircraft_types").joinpath("aircraft-equivalence.yaml").read_text()
        data = yaml.safe_load(ae)
        AircraftType._DB_EQUIVALENCE = data
        logger.debug(f"loaded {show_path(files('data.aircraft_types').joinpath('aircraft-equivalence.json'))}")
        logger.debug(f"loaded {len(AircraftType._DB_EQUIVALENCE)} aircraft equivalences")

    @staticmethod
    def getEquivalence(ac, redis=None):
        """
        Attempt to guess an aircraft code equivalence.
        Example: B777 ->["777", "B77L", "77L"...]
        The aircraft equivalence should be set as an aircraft performance data.

        :param      ac:   { parameter_description }
        :type       ac:   { type_description }
        """
        if redis is not None:
            prevdb = redis.client_info()["db"]
            redis.select(REDIS_DB.REF.value)
            k = key_path(REDIS_PREFIX.AIRCRAFT_EQUIS.value, ac)
            v = redis.smembers(k)
            redis.select(prevdb)
            if v is not None:
                for e in [a.decode("UTF-8") for a in v]:
                    ke = key_path(REDIS_PREFIX.AIRCRAFT_PERFS.value, e)
                    ve = rejson(redis=redis, key=ke, db=REDIS_DB.REF.value)
                    if ve is not None:
                        redis.select(prevdb)
                        return e
                logger.warning(f"no equivalence for {ac} ({v})")
                return None
            else:
                logger.warning(f"no equivalence for {ac}")
                return None

        if len(AircraftType._DB_EQUIVALENCE) == 0:
            AircraftType.loadAircraftEquivalences()
        for k, v in AircraftType._DB_EQUIVALENCE.items():
            if ac in v:
                return k
        logger.warning(f"no equivalence for {ac}")
        return None

    @staticmethod
    def find(icao: str, redis=None):
        """
        Returns aircraft type instance based on ICAO type code.

        :param      icao:  The icao
        :type       icao:  str
        """
        if redis is not None:
            k = key_path(REDIS_PREFIX.AIRCRAFT_TYPES.value, icao)
            ac = redis.get(k)
            if ac is not None:
                return AircraftType.fromInfo(info=ac)
            else:
                logger.warning(f"AircraftType::find: no such key {k}")
        return AircraftType._DB[icao] if icao in AircraftType._DB else None

    @classmethod
    def fromInfo(cls, info: str):
        at = AircraftType(orgId=info["actype-manufacturer"], classId=info["acclass"], typeId=info["actype"], name=info["acmodel"], data=info)
        # backward compatibility (to be removed later)
        at.rawdata["length"] = info["properties"]["length"]
        at.rawdata["wingspan"] = info["properties"]["wingspan"]
        return at

    def getKey(self):
        if self.iata is not None:
            return key_path(self.typeId, self.iata)
        return self.typeId

    def getInfo(self) -> dict:
        """
        Gets the information about an aircraft.
        """
        return {
            "actype-manufacturer": self.orgId,
            "class": self.classId,
            "actype": self.typeId,
            "acmodel": self.name,
            "acclass": self._ac_class,
            "properties": {"length": self.getProp("length"), "wingspan": self.getProp("wingspan")},
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
                try:
                    return convert.feet_to_meters(float(self.rawdata["Wingspan- ft"]))
                except ValueError:
                    return None
            if name == "length" and "Length- ft" in self.rawdata:
                try:
                    return convert.feet_to_meters(float(self.rawdata["Length- ft"]))
                except ValueError:
                    return None
            return self.rawdata[name] if name in self.rawdata else None
        logger.warning(f"AircraftType {self.typeId} no raw data for {name}")
        return None

    def setClass(self, ac_class: str = None):
        """
        Set an aircraft type class for alternative or similar characteristic lookup.
        Current implementation returns letter A-F depending on aircraft size and weight.

        :returns:   The class.
        :rtype:     str
        """
        ws = self.getProp("wingspan")
        ln = self.getProp("length")
        if ac_class is None and ws is not None:
            try_class = "A"
            if ws > 78:
                try_class = "F"
            elif ws > 65:
                try_class = "E"
            elif ws > 50:
                try_class = "D"
            elif ws > 40:
                try_class = "C"
            elif ws > 32:
                try_class = "B"
            # logger.warning(f"guessed class {try_class} for {self.typeId} (wingspan={ws})")
            ac_class = try_class

        if ac_class is not None:
            if ac_class in "ABCDEF":
                # logger.debug(f"{self.name} class {ac_class} {'<' * 40}")
                self._ac_class = ac_class
            else:
                logger.warning(f"{self.name} invalid class {ac_class}")
        else:
            pass
            # logger.warning(f"{self.name} cannot determine class")

    def getClass(self) -> str:
        """
        Returns an aircraft type class for alternative or similar characteristic lookup.
        If valid_only, returns letter A-F depending on aircraft size and weight otherwise None.

        :returns:   The class.
        :rtype:     str
        """
        if self._ac_class is not None:
            return self._ac_class
        # tries to set it
        self.setClass()
        if self._ac_class is not None:
            return self._ac_class
        logger.warning(f"no class for {self.typeId}")
        return _STD_CLASS

    def save(self, base, redis):
        """
        Saves aircraft model information and characteristics to cache.

        :param      base:   The base
        :type       base:   { type_description }
        :param      redis:  The redis
        :type       redis:  { type_dexscription }
        """
        # redis.set(key_path(base, self.getKey()), json.dumps(self.getInfo()))
        redis.json().set(key_path(base, self.getKey()), "$", self.getInfo())


class AircraftTypeWithPerformance(AircraftType):
    """
    The AircraftPerformance class augments the information available from the global aircraft database (AircraftType)
    with aircraft performance data necessary for the computation of its movements.

    .. code-block:: json

        {
            "icao": "A321",
            "iata": "321/32S",
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
            "wingspan": 30.56,
            "length": 28.45
        }

    """

    _DB_PERF = {}

    def __init__(self, orgId: str, classId: str, typeId: str, name: str, data=None):
        """Defines an aircraft and its associated kinematic performance data.

        [description]

        Args:
            orgId (str): [description]
            classId (str): [description]
            typeId (str): [description]
            name (str): [description]
            data ([type]): [description] (default: `None`)
        """
        AircraftType.__init__(self, orgId=orgId, classId=classId, typeId=typeId, name=name, data=data)
        self.perfraw = None  # Also used as a flag to see if loaded
        self.gseprofile = None  # relative position of ground vehicle around the aircraft
        self.tarprofile = None  # relative scheduled time of services
        self.display_name = None

        self.perfdata = None  # computed
        self.available = False
        # try:
        #     self.wrap = WRAP(typeId, use_synonym=True)
        # except:
        #     logger.info(f"wrap not available for {typeId}")

    @staticmethod
    def loadAll():
        """
        Load all aircraft performance data files for all aircrafts where it is available.
        """
        ac = files("data.aircraft_types").joinpath("aircraft-performances.json").read_text()
        jsondata = json.loads(ac)
        for ac in jsondata.keys():
            actype = AircraftType.find(ac)
            if actype is not None:
                acperf = AircraftTypeWithPerformance(actype.orgId, actype.classId, actype.typeId, actype.name, actype.rawdata)
                acperf.display_name = acperf.orgId + " " + acperf.name
                acperf.perfraw = jsondata[ac]
                acperf.setClass()
                if acperf.check_availability():  # sets but also returns availability
                    acperf.toSI()
                AircraftTypeWithPerformance._DB_PERF[ac] = acperf
            else:
                logger.warning(f"AircraftType {ac} not found")

        cnt = len(list(filter(lambda a: a.available, AircraftTypeWithPerformance._DB_PERF.values())))
        logger.debug(f"loaded {show_path(files('data.aircraft_types').joinpath('aircraft-performances.json'))}")
        logger.debug(f"loaded {len(AircraftTypeWithPerformance._DB_PERF)} aircraft types with their performances, {cnt} available")
        logger.debug(f"{list(map(lambda f: (f.typeId, f.getIata()), AircraftTypeWithPerformance._DB_PERF.values()))}")

    @staticmethod
    def find(icao: str, redis=None):
        """
        Returns AircraftPerformance type instance based on ICAO type code.

        :param      icao:  The icao
        :type       icao:  str
        """
        if redis is not None:
            k = key_path(REDIS_PREFIX.AIRCRAFT_PERFS.value, icao)
            ap = rejson(redis=redis, key=k, db=REDIS_DB.REF.value)
            if ap is not None:
                logger.debug(f"AircraftPerformance::find: loaded {icao} from redis")
                return AircraftTypeWithPerformance.fromInfo(info=ap)
            else:
                logger.warning(f"AircraftPerformance::find: no such key {k}")
        return AircraftTypeWithPerformance._DB_PERF[icao] if icao in AircraftTypeWithPerformance._DB_PERF else None

    @staticmethod
    def findAircraftForRange(reqrange: int, pax: int = 0, cargo: int = 0, restricted_list: list = None, redis=None):
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
        valid_list = restricted_list if restricted_list is not None else AircraftTypeWithPerformance._DB_PERF.keys()
        for ac in valid_list:
            acperf = None
            if redis:
                AircraftTypeWithPerformance.findAircraftByType(actype=ac, acsubtype=None, redis=redis)
            else:
                acperf = AircraftTypeWithPerformance._DB_PERF[ac]
            if acperf is not None and acperf.available and ("cruise_range" in acperf.perfraw):
                r = convert.km_to_nm(float(acperf.perfraw["cruise_range"]))  # km
                if r > reqrange:
                    rd = r - reqrange
                    # logger.debug("can use %s: %f (%f)" % (ac, r, rd))
                    if rd < rdiff:
                        rdiff = rd
                        best = acperf
                        # logger.debug("best %f" % rdiff)
        return best

    @staticmethod
    def findAircraftByType(actype: str, acsubtype: str, redis=None):
        """
        Returns existing AircraftPerformance aircraft or None if aircraft cannot be found.

        :param      actype:     The actype, loosely connected to ICAO type code
        :type       actype:     str
        :param      acsubtype:  The acsubtype, loosely connected to AITA type code
        :type       acsubtype:  str

        :returns:   The aircraft performance.
        :rtype:     AircraftPerformance
        """
        if redis is not None:
            k = rejson(redis=redis, key=key_path(REDIS_PREFIX.AIRCRAFT_PERFS.value, actype), db=REDIS_DB.REF.value)
            if k is not None:
                logger.debug(f"found type {actype}")
                return actype

            k = rejson(redis=redis, key=key_path(REDIS_PREFIX.AIRCRAFT_PERFS.value, acsubtype), db=REDIS_DB.REF.value)
            if k is not None:
                logger.debug(f"found sub type {acsubtype}")
                return acsubtype

            eq = AircraftTypeWithPerformance.getEquivalence(actype, redis)
            if eq is not None:
                logger.debug(f"found equivalence {eq} for type {actype}")
                return eq
            eq = AircraftTypeWithPerformance.getEquivalence(acsubtype, redis)
            if eq is not None:
                logger.debug(f"found equivalence {eq} for subtype {acsubtype}")
                return eq

        else:
            if actype in AircraftTypeWithPerformance._DB_PERF.keys():
                logger.debug(f"found type {actype}")
                return actype
            if acsubtype in AircraftTypeWithPerformance._DB_PERF.keys():
                logger.debug(f"found sub type {acsubtype}")
                return acsubtype
            eq = AircraftTypeWithPerformance.getEquivalence(actype)
            if eq is not None:
                logger.debug(f"found equivalence {eq} for type {actype}")
                return eq
            eq = AircraftTypeWithPerformance.getEquivalence(acsubtype)
            if eq is not None:
                logger.debug(f"found equivalence {eq} for subtype {acsubtype}")
                return eq
            logger.warning(f"no aircraft for {actype}, {acsubtype}")

        return None

    @staticmethod
    def getCombo(redis=None):
        """
        Gets a list of pairs (code, description) for all aircafts in the AircraftPerformance database.
        """
        if redis is not None:
            aperfs = rejson(redis=redis, key=REDIS_PREFIX.AIRCRAFT_PERFS.value, db=REDIS_DB.REF.value)
            return [(ac, ac) for ac in aperfs.keys()]

        l = filter(lambda a: a.available, AircraftTypeWithPerformance._DB_PERF.values())
        a = [(a.typeId, a.display_name) for a in sorted(l, key=operator.attrgetter("display_name"))]
        return a

    def getKey(self):
        return self.typeId
        # iata = self.getIata()
        # if iata is not None:
        #     if len(iata) > 0:
        #         return iata[0]
        # return super().getId()

    @classmethod
    def fromInfo(cls, info: str):
        acperf = AircraftTypeWithPerformance(
            orgId=info["base-type"]["actype-manufacturer"],
            classId=info["base-type"]["acclass"],
            typeId=info["base-type"]["actype"],
            name=info["base-type"]["acmodel"],
            data=info["performances-raw"],
        )
        acperf.display_name = acperf.orgId + " " + acperf.name
        acperf.perfraw = info["performances-raw"]
        acperf.perfdata = info["performances"]
        acperf._ac_class = info["class"]
        acperf.tarprofile = info["profile-tar"]
        acperf.gseprofile = info["profile-gse"]
        return acperf

    def getInfo(self):
        return {
            "type": "aircraft-performances",
            "base-type": super().getInfo(),
            "class": self._ac_class,
            "performances-raw": self.perfraw,
            "performances": self.perfdata,
            "profile-tar": self.tarprofile,
            "profile-gse": self.gseprofile,
        }

    def getIata(self):
        """
        Gets the IATA code of an aircraft type if available.
        """
        iata = self.perfraw["iata"] if ("iata" in self.perfraw and self.perfraw["iata"] is not None and self.perfraw["iata"] != "nodata") else None
        return str(iata).split("/") if iata else []

    def load(self, redis=None):
        """
        Loads additional aircraft performance or characteristic data
        necessary for the application.
        It loads Ground Support Vehicle Profile (how GSE vehicle arrange around the aircraft on the apron).
        It also loads Turnaround Profile, a typical service schedule pattern for arrival or departure service scheduling.
        """
        if self.perfraw is None:
            status = self.loadPerformance(redis=redis)
            if not status[0]:
                return status

            # status = self.loadTurnaroundProfiles(redis=redis)
            # if not status[0]:
            #     return status

            status = self.loadGSEProfile(redis=redis)
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
        filename = os.path.join(DATA_DIR, AIRCRAFT_TYPE_DATABASE, self.typeId.upper() + extension)
        if os.path.exists(filename):
            with open(filename, "r") as file:
                if filename[-5:] == ".yaml":
                    data = yaml.safe_load(file)
                else:  # JSON or GeoJSON
                    data = json.load(file)
            logger.debug(f"loaded {filename} for aircraft type {self.typeId.upper()}")
        else:  # fall back on aircraft performance category (A-F)
            logger.warning(f"file not found {filename}, using default")
            filename = os.path.join(DATA_DIR, AIRCRAFT_TYPE_DATABASE, self.getClass() + extension)
            if os.path.exists(filename):
                with open(filename, "r") as file:
                    if filename[-5:] == ".yaml":
                        data = yaml.safe_load(file)
                    else:  # JSON or GeoJSON
                        data = json.load(file)
                logger.debug(f"loaded class {filename} data for aircraft class {self.getClass()}")
            else:
                logger.warning(f"file not found {filename}")
                filename = os.path.join(DATA_DIR, AIRCRAFT_TYPE_DATABASE, _STD_CLASS + extension)
                if os.path.exists(filename):
                    with open(filename, "r") as file:
                        if filename[-5:] == ".yaml":
                            data = yaml.safe_load(file)
                        else:  # JSON or GeoJSON
                            data = json.load(file)
                    logger.debug(f"loaded {filename} standard data for aircraft, ignoring model")
                else:
                    logger.warning(f"standard data file {filename} for aircraft not found")
                    logger.warning(f"no data file for {self.typeId.upper()}")
        return data

    def loadPerformance(self, redis=None):
        """
        Loads a performance data file for a single aircraft type.
        """
        if self.perfraw is None:
            if redis is not None:
                key = key_path(REDIS_PREFIX.AIRCRAFT_PERFS.value, self.typeId.upper())
                r = rejson(redis=redis, key=key, db=REDIS_DB.REF.value)
                if r is None:
                    logger.debug(f"no profile for {self.typeId.upper()}, trying class {self._ac_class} ({key})")
                    key = key_path(REDIS_PREFIX.AIRCRAFT_PERFS.value, self._ac_class)
                    r = rejson(redis=redis, key=key, db=REDIS_DB.REF.value)
                    if r is None:
                        logger.warning(f"no turnaround profile data file for class {self._ac_class} ({key})")
                        return (False, "AircraftPerformance::loadPerformance: no profile found in Redis")
                logger.debug(f"loaded from redis for {self.typeId.upper()}")
            else:
                data = self.loadFromFile(".json")
                if data is not None:
                    self.perfraw = data
                    if self.check_availability():
                        self.toSI()
                else:
                    logger.warning(f"no performance data file for {self.typeId.upper()}")
        logger.debug(f"loaded for {self.typeId.upper()}")
        return [True, "AircraftPerformance::loadPerformance: loaded"]

    def loadGSEProfile(self, redis=None):
        """
        Loads a ground support vehicle arrangement data file for a single aircraft type.
        """
        if self.gseprofile is None:
            if redis is not None:
                key = key_path(REDIS_PREFIX.AIRCRAFT_GSEPROFILES.value, self.typeId.upper())
                r = rejson(redis=redis, key=key, db=REDIS_DB.REF.value)
                pty = f"aircraft model {self.typeId.upper()}"
                if r is None:
                    logger.debug(f"no profile for {self.typeId.upper()}, trying class {self._ac_class} ({key})")
                    key = key_path(REDIS_PREFIX.AIRCRAFT_GSEPROFILES.value, self._ac_class)
                    r = rejson(redis=redis, key=key, db=REDIS_DB.REF.value)
                    pty = f"aircraft class {self._ac_class}"
                    if r is None:
                        logger.warning(f"no turnaround profile data file for class {self._ac_class} ({key}), trying default class {_STD_CLASS}")
                        key = key_path(REDIS_PREFIX.AIRCRAFT_GSEPROFILES.value, _STD_CLASS)
                        r = rejson(redis=redis, key=key, db=REDIS_DB.REF.value)

                        if r is None:
                            logger.error(f"no turnaround profile data file for standard class {_STD_CLASS} ({key})")
                            return (False, "AircraftPerformance::loadGSEProfile: no profile found in Redis")
                        pty = f"default class {_STD_CLASS}"
                self.gseprofile = r
                logger.debug(f"using profile for {self.typeId.upper()} ({pty}, {key})")
            else:
                data = self.loadFromFile("-gseprf.yaml")
                if data is not None:
                    self.gseprofile = data
                else:
                    logger.warning(f"no GSE profile data file for {self.typeId.upper()}")
        return [True, "AircraftPerformance::loadGSEProfile: loaded"]

    def check_availability(self):
        """
        Check whether all perfomance data is available for this aircraft type.
        If not, the aircraft cannot be used in the application (insufficient data available).
        """
        if self._ac_class is None:
            logger.warning(f"{self.typeId} has no class")
            return False

        max_ceiling = self.get("max_ceiling")  # this is a FL
        if max_ceiling is None:
            logger.warning(f"no max ceiling for: {self.typeId}")
            return False

        param_list = ["takeoff_distance", "takeoff_speed", "initial_climb_speed", "initial_climb_vspeed"]
        param_list = param_list + ["cruise_speed", "cruise_range"]
        param_list = param_list + ["approach_speed", "approach_vspeed", "landing_speed", "landing_distance"]
        param_list = param_list + ["length", "wingspan"]

        param_list = param_list + ["climbFL150_speed", "climbFL150_vspeed"]
        if max_ceiling > 150:
            param_list = param_list + ["climbFL240_speed", "climbFL240_vspeed"]
            param_list = param_list + ["descentFL100_speed", "descentFL100_vspeed"]
        if max_ceiling > 240:
            param_list = param_list + ["climbmach_mach", "climbmach_vspeed"]
            param_list = param_list + ["descentFL240_mach", "descentFL240_vspeed"]

        # @todo:
        # For ATRXX, max_ceiling > 240 and max_ceiling < 300,
        # should accept climb/decent at same rate as climbFL240_speed, climbFL240_vspeed, descentFL100_speed, descentFL100_vspeed
        # even if not climbmach_mach, descentFL240_mach, etc.
        # Need to accept here, and adjust climbToCruise() and descentToFL240().

        for name in param_list:
            if name not in self.perfraw or self.perfraw[name] == "no data":
                logger.warning(f"no {name} for: {self.typeId}, rejecting")
                return False
        self.available = True
        # logger.warning(f"{self.typeId} is ok")
        return True

    def setClass(self, ac_class: str = None):
        """
        Set an aircraft type class for alternative or similar characteristic lookup.
        Current implementation returns letter A-F depending on aircraft size and weight.

        :returns:   The class.
        :rtype:     str
        """
        ws = self.get("wingspan")
        ln = self.get("length")
        if self._ac_class is None and ac_class is None and ws is not None:
            try_class = "A"  # ICAO Aerodrome Reference Code Code Element 2, mainly used for taxiway design
            if ws > 65:
                try_class = "F"
            elif ws > 52:
                try_class = "E"
            elif ws > 36:
                try_class = "D"
            elif ws > 24:
                try_class = "C"
            elif ws > 15:
                try_class = "B"
            # logger.debug(f"guessed class {try_class} for {self.typeId}")
            # logger.debug(f"{self.typeId}: wingspan={ws}, length={ln}")
            ac_class = try_class

        if ac_class is not None and ac_class in "ABCDEF":
            self._ac_class = ac_class
        else:
            logger.warning(f"invalid class {ac_class} for {self.typeId}")

    def toSI(self):
        """
        Converts numeric performance data to Système International.
        Uses meters, seconds, meter per second, hecto-pascal, etc.
        """
        SHOW_CONVERT = False
        ROUND = 3
        if self.perfdata is None:
            self.perfdata = {}
            err = 0

            for name in [
                "initial_climb_vspeed",
                "climbFL150_vspeed",
                "climbFL240_vspeed",
                "climbmach_vspeed",
                "descentFL240_vspeed",
                "descentFL100_vspeed",
                "approach_vspeed",
            ]:  # vspeed: ft/m -> m/s
                if name in self.perfraw and self.perfraw[name] != "no data":
                    self.perfdata[name] = round(convert.fpm_to_ms(self.perfraw[name]), ROUND)
                    if SHOW_CONVERT:
                        logger.debug(f"{self.name}: {name}: {self.perfraw[name]} ft/min -> {self.perfdata[name]} m/s")
                else:
                    logger.warning(f"{self.name} no value for: {name}")
                    err = err + 1

            for name in [
                "takeoff_speed",
                "initial_climb_speed",
                "climbFL150_speed",
                "climbFL240_speed",
                "cruise_speed",
                "descentFL100_speed",
                "approach_speed",
                "landing_speed",
            ]:  # speed: kn -> m/s
                if name in self.perfraw and self.perfraw[name] != "no data":
                    self.perfdata[name] = round(convert.kn_to_ms(kn=float(self.perfraw[name])), ROUND)
                    if SHOW_CONVERT:
                        logger.debug(f"{self.name}: {name}: {self.perfraw[name]} kn -> {self.perfdata[name]} m/s, {self.perfdata[name] * 3.6} km/h")
                else:
                    logger.warning(f"{self.name} no value for: {name}")
                    err = err + 1

            for name in ["climbmach_mach", "descentFL240_mach"]:  # speed: mach -> m/s
                if name in self.perfraw and self.perfraw[name] != "no data":
                    kmh = convert.mach_to_kmh(float(self.perfraw[name]), 24000)
                    self.perfdata[name] = round(convert.kmh_to_ms(kmh=kmh), ROUND)
                    if SHOW_CONVERT:
                        logger.debug(f"{self.name}: {name}: {self.perfraw[name]} mach -> {self.perfdata[name]} m/s, {kmh} km/h (FL240)")
                else:
                    logger.warning(f"{self.name} no value for: {name}")
                    err = err + 1

            for name in ["cruise_mach"]:  # speed: mach -> m/s
                if name in self.perfraw and self.perfraw[name] != "no data":
                    kmh = convert.mach_to_kmh(float(self.perfraw[name]), 30000)
                    self.perfdata[name] = round(convert.kmh_to_ms(kmh=kmh), ROUND)
                    if SHOW_CONVERT:
                        logger.debug(f"{self.name}: {name}: {self.perfraw[name]} mach -> {self.perfdata[name]} m/s, {kmh} km/h (FL300)")
                else:
                    logger.warning(f"{self.name} no value for: {name}")
                    err = err + 1

        # copy others verbatim
        for n in self.perfraw.keys():
            if n not in self.perfdata.keys():
                if self.perfraw[n] != "no data":
                    self.perfdata[n] = self.perfraw[n]
                else:
                    logger.warning(f"{self.name} no value for: {n}")

    def get(self, name: str):
        """
        Get performance raw value

        :param      name:  The name
        :type       name:  str
        """
        val = self.perfraw.get(name)
        if val is None:
            logger.warning(f"no value for: {name}")
            return None
        return val

    def getSI(self, name: str):
        """
        Get performance value in SI unit system.

        :param      name:  The name
        :type       name:  str
        """
        val = self.perfdata.get(name)
        if val is None:
            logger.warning(f"no value for: {name}")
            return None
        return val

    def FlightLevelFor(self, reqrange: int):
        """
        Estimates a flight level for supplied range.
        (No need to go FL340 for a 200km flight. Not a formal computation, just a reasonable suggestion.)
        The aircraft type max_ceiling is taken into consideration.
        Returns flight level in FEETS / 100

        :param      reqrange:  The reqrange
        :type       reqrange:  int
        """
        max_ceiling = self.get("max_ceiling")
        if max_ceiling is None:
            logger.warning(f"no max ceiling for: {self.typeId}, assuming max ceiling is FL300")
            max_ceiling = 300
        # get conservative
        max_ceiling = int(0.95 * max_ceiling)
        # Set Flight Level for given flight range in km.
        if reqrange < 300:
            return min(200, max_ceiling)
        if reqrange < 500:
            return min(240, max_ceiling)
        if reqrange < 1000:
            return min(280, max_ceiling)
        if reqrange < 2000:
            return min(340, max_ceiling)
        return min(430, max_ceiling)

    def CruiseSpeedFor(self, reqfl: int) -> int | float:
        """
        Returns cruise speed according to flight level.
        Returns cruise speed in IMPERIAL UNITS

        :param      reqfl:  The required flight level
        :type       reqfl:  int
        """

        if reqfl < 100:
            return min(250, self.get(ACPERF.climbFL150_speed))
        if reqfl < 240:
            return self.get(ACPERF.climbFL240_speed)
        if reqfl < 240:
            return self.get(ACPERF.climbmach_mach)
        return self.get(ACPERF.cruise_mach)

    def getClimbSpeedRangeForAlt(self, alt: float) -> SPEED_RANGE:
        if alt <= convert.feet_to_meters(1500):
            return SPEED_RANGE.SLOW
        elif alt <= convert.feet_to_meters(15000):
            return SPEED_RANGE.FL150
        elif alt <= convert.feet_to_meters(24000):
            return SPEED_RANGE.FL240
        elif alt > convert.feet_to_meters(24000):
            return SPEED_RANGE.FAST
        logger.warning(f"invalid altitude {alt}, cannot convert to speed range")
        return None

    def getDescendSpeedRangeForAlt(self, alt):
        if alt > convert.feet_to_meters(24000):
            return SPEED_RANGE.FAST
        elif alt > convert.feet_to_meters(10000):
            return SPEED_RANGE.FL240
        elif alt > convert.feet_to_meters(3000):
            return SPEED_RANGE.FL150
        return SPEED_RANGE.SLOW

    def getClimbSpeedAndVSpeedForAlt(self, alt) -> Tuple[float, float]:
        if alt <= convert.feet_to_meters(1500):
            return self.getSI(ACPERF.initial_climb_speed), self.getSI(ACPERF.initial_climb_vspeed)
        elif alt < convert.feet_to_meters(15000):
            return self.getSI(ACPERF.climbFL150_speed), self.getSI(ACPERF.climbFL150_vspeed)
        elif alt < convert.feet_to_meters(24000):
            return self.getSI(ACPERF.climbFL240_speed), self.getSI(ACPERF.climbFL240_vspeed)
        # convert mach to speed
        cms = convert.kmh_to_ms(kmh=convert.mach_to_kmh(self.getSI(ACPERF.climbmach_mach), alt))  # should not be 0, we need to know...
        return cms, self.getSI(ACPERF.climbmach_vspeed)

    def getDescendSpeedAndVSpeedForAlt(self, alt) -> Tuple[float, float]:
        if alt > convert.feet_to_meters(24000):
            kmh = convert.mach_to_kmh(self.get(ACPERF.descentFL240_mach), alt)
            ms = convert.kmh_to_ms(kmh=kmh)
            return ms, self.getSI(ACPERF.descentFL240_vspeed)
        elif alt > convert.feet_to_meters(10000):
            return self.getSI(ACPERF.descentFL100_speed), self.getSI(ACPERF.descentFL100_vspeed)
        elif alt > convert.feet_to_meters(3000):
            return self.getSI(ACPERF.approach_speed), self.getSI(ACPERF.approach_vspeed)
        return self.getSI(ACPERF.landing_speed), self.getSI(ACPERF.approach_vspeed)

        if alt <= convert.feet_to_meters(1500):
            return self.getSI(ACPERF.initial_climb_speed), self.getSI(ACPERF.initial_climb_vspeed)
        elif alt < convert.feet_to_meters(15000):
            return self.getSI(ACPERF.climbFL150_speed), self.getSI(ACPERF.climbFL150_vspeed)
        elif alt < convert.feet_to_meters(24000):
            return self.getSI(ACPERF.climbFL240_speed), self.getSI(ACPERF.climbFL240_vspeed)
        # convert mach to speed
        cms = convert.kmh_to_ms(kmh=convert.mach_to_kmh(self.getSI(ACPERF.climbmach_mach), alt))  # should not be 0, we need to know...
        return cms, self.getSI(ACPERF.climbmach_vspeed)

    def getROCDistanceForAlt(self, alt):
        if alt <= convert.feet_to_meters(1500):
            return self.getSI(ACPERF.initial_climb_vspeed) / self.getSI(ACPERF.initial_climb_speed)
        elif alt < convert.feet_to_meters(15000):
            return self.getSI(ACPERF.climbFL150_vspeed) / self.getSI(ACPERF.climbFL150_speed)
        elif alt < convert.feet_to_meters(24000):
            return self.getSI(ACPERF.climbFL240_vspeed) / self.getSI(ACPERF.climbFL240_speed)
        return self.getSI(ACPERF.climbmach_vspeed) / self.getSI(ACPERF.climbmach_mach)

    def getRODDistanceForAlt(self, alt):
        if alt > convert.feet_to_meters(24000):
            return self.getSI(ACPERF.descentFL240_vspeed) / self.getSI(ACPERF.descentFL240_mach)
        elif alt > convert.feet_to_meters(10000):
            return self.getSI(ACPERF.descentFL100_vspeed) / self.getSI(ACPERF.descentFL100_speed)
        elif alt > convert.feet_to_meters(3000):
            return self.getSI(ACPERF.approach_vspeed) / self.getSI(ACPERF.approach_speed)
        return self.getSI(ACPERF.approach_vspeed) / self.getSI(ACPERF.landing_speed)

    def perfs(self):
        """
        Convenience function to print all aircraft available performance data.
        """
        for name in self.perfdata.keys():
            logger.debug(f"{name} {self.get(name)} {self.getSI(name)}")

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
        # logger.debug("%s from %f to %f at %f m/s during %f, move %f at %f m/s" % (self.name, altstart, altend, vspeed, t, d, speed))
        return (t, d, altend)

    def initialClimb(self, altstart, safealt: float = INITIAL_CLIMB_SAFE_ALT_M):
        """
        Alias to climb function for initialClimb speed and vspeed.

        :param      altstart:  The altstart
        :type       altstart:  { type_description }
        :param      safealt:   The safealt
        :type       safealt:   int
        """
        # Time to climb what is usually accepted as 1500ft AGL
        return self.climb(altstart, altstart + safealt, self.getSI(ACPERF.initial_climb_vspeed), self.getSI(ACPERF.initial_climb_speed))

    def climbToFL100(self, altstart):
        """
        Alias to climb function for initialClimb speed and vspeed.

        :param      altstart:  The altstart
        :type       altstart:  { type_description }
        :param      safealt:   The safealt
        :type       safealt:   int
        """
        # Time to climb what is usually accepted as 1500ft AGL
        return self.climb(altstart, convert.feet_to_meters(10000), self.getSI(ACPERF.climbFL150_vspeed), self.low_alt_max_speed(alt=altstart))

    def low_alt_max_speed(self, alt, speed=convert.kn_to_ms(LOW_ALT_MAX_SPEED)):
        """
        Alias to climb function for FL100 speed and vspeed.

        :param      altstart:  The altstart
        :type       altstart:  { type_description }
        :param      safealt:   The safealt
        :type       safealt:   int
        """
        # Time to climb what is usually accepted as 1500ft AGL
        if alt <= convert.feet_to_meters(LOW_ALT_ALT_FT):
            return min(speed, convert.kn_to_ms(LOW_ALT_MAX_SPEED))
        return speed

    def climbToFL150(self, altstart):
        """
        Alias to climb function for FL150 speed and vspeed.

        :param      altstart:  The altstart
        :type       altstart:  { type_description }
        :param      safealt:   The safealt
        :type       safealt:   int
        """
        # Time to climb what is usually accepted as 1500ft AGL
        return self.climb(altstart, convert.feet_to_meters(15000), self.getSI(ACPERF.climbFL150_vspeed), self.getSI(ACPERF.climbFL150_speed))

    def climbToFL180(self, altstart):
        """
        Alias to climb function for FL240 speed and vspeed.

        :param      altstart:  The altstart
        :type       altstart:  { type_description }
        :param      safealt:   The safealt
        :type       safealt:   int
        """
        # Time to climb what is usually accepted as 1500ft AGL
        return self.climb(altstart, convert.feet_to_meters(18000), self.getSI(ACPERF.climbFL240_vspeed), self.getSI(ACPERF.climbFL240_speed))

    def climbToFL240(self, altstart):
        """
        Alias to climb function for FL240 speed and vspeed.

        :param      altstart:  The altstart
        :type       altstart:  { type_description }
        :param      safealt:   The safealt
        :type       safealt:   int
        """
        # Time to climb what is usually accepted as 1500ft AGL
        return self.climb(altstart, convert.feet_to_meters(24000), self.getSI(ACPERF.climbFL240_vspeed), self.getSI(ACPERF.climbFL240_speed))

    def climbToCruise(self, altstart, altcruise):
        """
        Alias to climb function for cruise speed and vspeed.

        :param      altstart:  The altstart
        :type       altstart:  { type_description }
        :param      safealt:   The safealt
        :type       safealt:   int
        """
        # Time to climb what is usually accepted as 1500ft AGL
        avgalt = (altstart + altcruise) / 2
        avgspd = convert.kmh_to_ms(kmh=convert.mach_to_kmh(float(self.get(ACPERF.climbmach_mach)), avgalt))  # m/s
        return self.climb(altstart, altcruise, self.getSI(ACPERF.climbmach_vspeed), avgspd)

    #
    # Descent helper functions
    #
    # @todo: Should catch absence of descent speed
    #
    def descentToFL240(self, altcruise):
        """
        Alias to climb function to descent to FL240 speed and vspeed.

        :param      altstart:  The altstart
        :type       altstart:  { type_description }
        :param      safealt:   The safealt
        :type       safealt:   int
        """
        altend = convert.feet_to_meters(24000)
        avgalt = (altcruise + altend) / 2
        avgspd = convert.kmh_to_ms(kmh=convert.mach_to_kmh(float(self.get(ACPERF.descentFL240_mach)), avgalt))  # m/s
        return self.climb(altcruise, altend, -float(self.getSI(ACPERF.descentFL240_vspeed)), avgspd)

    def descentToFL180(self, altstart):
        """
        Alias to climb function to descent to FL100 speed and vspeed.

        :param      altstart:  The altstart
        :type       altstart:  { type_description }
        :param      safealt:   The safealt
        :type       safealt:   int
        """
        return self.climb(altstart, convert.feet_to_meters(18000), -float(self.getSI(ACPERF.descentFL100_vspeed)), float(self.getSI(ACPERF.descentFL100_speed)))

    def descentToFL100(self, altstart):
        """
        Alias to climb function to descent to FL100 speed and vspeed.

        :param      altstart:  The altstart
        :type       altstart:  { type_description }
        :param      safealt:   The safealt
        :type       safealt:   int
        """
        return self.climb(altstart, convert.feet_to_meters(10000), -float(self.getSI(ACPERF.descentFL100_vspeed)), float(self.getSI(ACPERF.descentFL100_speed)))

    def descentApproach(self, altstart, altend):
        """
        Alias to climb function to descent to approach speed and vspeed.

        :param      altstart:  The altstart
        :type       altstart:  { type_description }
        :param      safealt:   The safealt
        :type       safealt:   int
        """
        return self.climb(altstart, altend, -self.getSI(ACPERF.approach_vspeed), self.getSI(ACPERF.approach_speed))

    def descentFinal(self, altend, vspeed, safealt: float = FINAL_APPROACH_FIX_ALT_M):
        """
        Alias to climb function to descent from final to touch down.

        :param      altstart:  The altstart
        :type       altstart:  { type_description }
        :param      safealt:   The safealt
        :type       safealt:   int
        """
        return self.climb(altend + safealt, altend, -vspeed, self.getSI(ACPERF.landing_speed))

    def getGSEProfile(self, redis=None):
        if self.gseprofile is None:
            self.loadGSEProfile(redis=redis)

        if self.gseprofile is None:
            logger.warning(f"no turnaround profile for {self.typeId}")
            return None

        return self.gseprofile

    def inTarget(self, current, target: dict) -> dict:
        sok = current.speed > target["speed_min"] and current.speed < target["speed_max"]
        aok = current.altitude > target["altitude_min"] and current.speed < target["altitude_max"]
        tok = True
        if current.time is not None:
            tok = current.time > target["time_min"] and current.time < target["time_max"]
        return sok and aok and tok

    def getPotential(self, current, dist: float) -> dict:
        return {"speed_min": 0, "speed_max": 0, "altitude_min": 0, "altitude_min": 0, "time_max": 0, "time_min": 0, "time_curr": 0}

    def getTarget(self, current, dist: float, target: dict) -> dict:
        return {"speed": 0, "acceleration": 0, "altitude": 0, "vrate": 0, "time": 0}

    def yes_we_can(self, current, d, target):
        p = self.getPotential(current, d)
        return self.inTarget(target, p)

    def descend_rate(self, altitude: int, delta: int, wind_contrib: int = convert.nm_to_meters(10)) -> float:
        # Rule of thumb formula: (3 x height) + (1nm per 10kts of speed loss) + (1nm per 10kts of Tailwind Component)
        # 10kts = 5.144444 m/s
        # Tailwind: add 10nm for safety
        # Alt
        alt_contrib = 3 * delta
        # Speed
        speed, vspeed = self.getDescendSpeedAndVSpeedForAlt(altitude)
        speed2 = self.getSI(ACPERF.approach_speed)
        speed_diff = max(0, speed - speed2)
        speed_contrib = 0
        if speed_diff > 0:
            speed_contrib = convert.nm_to_meters(speed_diff / 5.1)  # 1nm per 5.14 m/s
        # Wind in parameters
        contrib = alt_contrib + speed_contrib + wind_contrib
        logger.debug(
            f"descend_rate a={round(alt_contrib/1000)}km + s={round(speed_contrib/1000)}km + w={round(wind_contrib/1000)}km = {round(contrib/1000)}km ({round(convert.km_to_nm(contrib/1000))}nm)"
        )
        return contrib


class AircraftClass(AircraftTypeWithPerformance):
    """
    An aircraft class is one particular aircraft type from A-F taxiway aicraft class type.
    It is an aircraft of typical class dimension, hence typical range, and capacity.
    It is used as a fallback in case of missing data for a given aircraft type.
    The ultimate fallback is non-existant class Z which is a typical everage size class C aircraft.
    All performance data MUST be present for an AicraftClass otherwise a error is reported.
    """

    _DB_AC_CLASS = {}

    def __init__(self, orgId: str, classId: str, typeId: str, name: str, data):
        AircraftTypeWithPerformance.__init__(self, orgId=orgId, classId=classId, typeId=typeId, name=name, data=data)

    @staticmethod
    def loadAll():
        """
        Loads the file self.filename and store its content in self.data.
        Based on the file extention, a proper loader is selected (text, json, yaml, or csv).

        :param      extension:  The extension
        :type       extension:  str
        """
        data = None
        for ac_class in "ABCDEF":
            filename = os.path.join(DATA_DIR, AIRCRAFT_TYPE_DATABASE, ac_class + ".json")
            if os.path.exists(filename):
                with open(filename, "r") as file:
                    data = json.load(file)
                    ac = data["icao"]
                    actype = AircraftType.find(ac)
                    if actype is not None:
                        acperf = AircraftClass(actype.orgId, actype.classId, actype.typeId, actype.name, data)
                        acperf.display_name = acperf.orgId + " " + acperf.name + " CLASS " + ac_class
                        acperf.perfraw = data
                        if acperf.check_availability():  # sets but also returns availability
                            acperf.toSI()
                        AircraftClass._DB_AC_CLASS[ac_class] = acperf
                    else:
                        logger.warning(f"AircraftClass {ac_class} not found")

        logger.debug(f"loaded {len(AircraftClass._DB_AC_CLASS)} aircraft classes with their performances")

    @staticmethod
    def getClass(ac_class: str = _STD_CLASS):
        return AircraftClass._DB_AC_CLASS[ac_class] if ac_class in "ABCDEF" else AircraftClass._DB_AC_CLASS[_STD_CLASS]


class Aircraft(Identity):
    """
    An aircraft servicing an airline route.
    """

    def __init__(self, registration: str, icao24: str, actype: AircraftTypeWithPerformance, operator: Company):
        """
        An aircraft servicing a flight.

        """
        Identity.__init__(self, orgId=operator.name, classId="Aircraft", typeId=actype.typeId, name=registration)
        self.registration = registration
        self.icao24 = icao24  # 6 hexadecimal digit string, ADS-B address
        self.operator = operator
        self.actype = actype
        self.callsign = None
        self.serial_number = None
        self.configuration = None  # "C36 Y247" or "C46 W43 Y208"

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

    def getId(self):
        return self.name  # == self.registration, (not correct, should return Indentity string)

    def getInfo(self) -> dict:
        """
        Gets information about this aircraft. Recurse to aircraft details (aircraft type, operator, etc).
        """
        return {
            "identity": self.getIdentity(),
            "actype": self.actype.getInfo(),
            "operator": self.operator.getInfo(),
            "acreg": self.registration,
            "icao24": self.icao24,
        }

    def getShortDesc(self):
        return super().getId()
        # return f"{self.registration} {self.actype.typeId} ({self.icao24})"

    def getClass(self):
        return self.actype.getClass()

    def save(self, redis):
        """
        Saves aircraft data and model information to cache.

        :param      redis:  The redis
        :type       redis:  { type_description }
        """
        if redis is None:
            return (True, "Aircraft::save: no Redis")

        prevdb = redis.client_info()["db"]
        redis.select(REDIS_DB.PERM.value)
        redis.set(key_path(REDIS_DATABASE.AIRCRAFTS.value, self.getId()), json.dumps(self.getInfo()))
        redis.select(prevdb)
        return (True, "Aircraft::save: saved")
