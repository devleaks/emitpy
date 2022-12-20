# Airspace class defined from X-Plane files and datasets.
#
import os.path
import re
import logging
import time
import csv
import json
from importlib_resources import files

from math import inf
from turfpy.measurement import distance

from emitpy.geo import FeatureWithProps
from emitpy.constants import REDIS_PREFIX, REDIS_DB
from emitpy.utils import key_path
from emitpy.parameters import XPLANE_DIR, DATA_DIR
from emitpy.utils import FT
from .aerospace import Aerospace, Terminal, Fix, SignificantPoint, AirwaySegment, CPIDENT, ControlledAirspace, Restriction
from .aerospace import NDB, VOR, LOC, MB, DME, GS, FPAP, GLS, LTPFTP, Hold

logger = logging.getLogger("XPAerospace")

AIRWAYS = {
    "LOW": 1,
    "HIGH": 2
}

DIRECTION = {
    "NONE": "N",
    "FORWARD": "F",
    "BACKWARD": "B"
}

NAVAIDS = {
    "NDB": 2,
    "VOR": 3,
    "ILSLOC": 4,
    "LOCLOC": 5,
    "GS": 6,
    "OM": 7,
    "MM": 8,
    "IM": 9,
    "DME": 12,
    "DMESA": 13,
    "FPAP": 14,
    "GLS": 15,
    "LTPFTP": 16
}

# For airways
FIX_TYPE = {
    2: "NDB",
    3: "VHF",
    11: "Fix"
}

LOCAL_HOLDS_ONLY = False

DEFAULT_DATA_DIR = os.path.join(XPLANE_DIR, "Resources", "default data")
CUSTOM_DATA_DIR  = os.path.join(XPLANE_DIR, "Custom Data")


##########################
#
# A I R   S P A C E   D A T A   I S S U E D   F R O M   X -P L A N E
# (Alternatives are Navigraph, ARIAC 424, etc.)
#
class XPAerospace(Aerospace):
    """
    Airspace definition based on X-Plane data.
    """
    def __init__(self, bbox=None, load_airways: bool = False):
        Aerospace.__init__(self, bbox, load_airways=load_airways)

        self._cached_vectex_ids = None
        self._cached_vectex_idents = None
        self.airports_icao = {}
        self.airports_iata = {}

        self.basename = DEFAULT_DATA_DIR
        fn = os.path.join(CUSTOM_DATA_DIR, "earth_nav.dat")
        if os.path.exists(fn):
            logger.info(f":init: custom data directory exist, using it")
            self.basename = CUSTOM_DATA_DIR


    def setAiracCycle(self, str_in: str):
        """
        Attempts to find Airac Cycle from either navdata cycle_info.txt file
        or X-Plane earth_nav.dat I line (information)

        earth_awy.dat:1100 Version - data cycle 1802, build 20200426, metadata AwyXP1100. Copyright (c) 2020 Navigraph, Datasource Jeppesen
        earth_fix.dat:1101 Version - data cycle 1802, build 20200426, metadata FixXP1101. Copyright (c) 2020 Navigraph, Datasource Jeppesen
        earth_hold.dat:1140 Version - data cycle 1802, build 20200426, metadata HoldXP1140. Copyright (c) 2020 Navigraph, Datasource Jeppesen
        earth_mora.dat:1150 Version - data cycle 1802, build 20200426, metadata MORAXP1150. Copyright (c) 2020 Navigraph, Datasource Jeppesen
        earth_msa.dat:1150 Version - data cycle 1802, build 20200426, metadata MSAXP1150. Copyright (c) 2020 Navigraph, Datasource Jeppesen
        earth_nav.dat:1150 Version - data cycle 1802, build 20200623, metadata NavXP1150. Copyright (c) 2020 Navigraph, Datasource Jeppesen

        """
        cycle = str_in.strip()
        if len(str_in) > 4:
            m = re.findall("data cycle ([0-9]{4})", str_in)
            cycle = None
            if len(m) == 1:
                cycle = m[0]
            elif len(m) > 1:
                cycle = m[0]
                logger.warning(f":setAiracCycle: ambiguous data cycle '{str_in}'")
            else:
                logger.debug(f":setAiracCycle: no airac cycle in '{str_in}'")
                return None

        if self.airac_cycle is None:
            self.airac_cycle = cycle
            logger.info(f":setAiracCycle: airac cycle {cycle} set")
        elif cycle != self.airac_cycle:
            logger.warning(f":setAiracCycle: multiple data cycle airspace={self.airac_cycle}, found={cycle}")
        else:
            logger.debug(f":setAiracCycle: airac cycle {cycle} ok")

        return cycle


    def getAiracCycle(self):
        if self.airac_cycle is None:
            logger.warning(f":getAiracCycle: airact cycle not set")
        return self.airac_cycle


    def loadAirports(self):
        """
        Loads all airports from a csv file.
        (From https://ourairports.com/data/)
        Source can be changed as needed.
        """
        startLen = len(self.vert_dict.keys())
        count = 0
        filename = os.path.join(DATA_DIR, "airports", "airports.csv")
        file = open(filename, "r")
        logger.info(":loadAirports: from %s.", filename)
        self.setAiracCycle(filename)
        csvdata = csv.DictReader(file)

        for r in csvdata:
            # Our Airport:
            # {
            #     "id": 2155,
            #     "ident": "EBBR",
            #     "type": "large_airport",
            #     "name": "Brussels Airport",
            #     "latitude_deg": 50.901401519800004,
            #     "longitude_deg": 4.48443984985,
            #     "elevation_ft": 184,
            #     "continent": "EU",
            #     "iso_country": "BE",
            #     "iso_region": "BE-BRU",
            #     "municipality": "Brussels",
            #     "scheduled_service": "yes",
            #     "gps_code": "EBBR",
            #     "iata_code": "BRU",
            #     "local_code": "",
            #     "home_link": "http://www.brusselsairport.be/en/",
            #     "wikipedia_link": "https://en.wikipedia.org/wiki/Brussels_Airport",
            #     "keywords": ""
            # }
            #
            lat = float(r["latitude_deg"]) if r["latitude_deg"] != "" else 0.0
            lon = float(r["longitude_deg"]) if r["longitude_deg"] != "" else 0.0
            if lat != 0.0 or lon != 0.0:
                alt = float(r["elevation_ft"])*FT if r["elevation_ft"] != "" else None
                apt = Terminal(name=r["ident"], lat=lat, lon=lon, alt=alt, iata=r["iata_code"], longname=r["name"], country=r["iso_country"], city=r["municipality"])
                self.airports_iata[r["iata_code"]] = apt
                self.airports_icao[r["ident"]] = apt
                self.add_vertex(apt)
                count += 1
            else:
                logger.warning(":loadAirports: invalid airport data %s.", line)

        file.close()

        logger.debug(":loadAirports: %d/%d airports loaded.", len(self.vert_dict.keys()) - startLen, count)
        return [True, "XPAerospace::Airport loaded"]


    def getAirportIATA(self, iata):
        """
        Returns airport from airspace airport database with matching IATA code.

        :param      iata:  The iata
        :type       iata:  { type_description }
        """
        return self.airports_iata[iata] if iata in self.airports_iata.keys() else None

    def getAirportICAO(self, icao):
        """
        Returns airport from airspace airport database with matching ICAO code.

        :param      iata:  The iata
        :type       iata:  { type_description }
        """
        return self.airports_icao[icao] if icao in self.airports_icao.keys() else None

    def checkFile(self, filename):
        KEY_HEADER = "^([\\d]{4}) Version - data cycle ([\\d]{4}), build ([\\d]{8}), metadata ([\\w]+). (.*)"
        file = open(filename, "r")
        line = file.readline()
        line.strip()
        while line:
            if line == "":
                pass
            if re.match("^I", line, flags=0):
                pass
            # 1150 Version - data cycle 1802, build 20200623, metadata NavXP1150. Copyright (c) 2020 Navigraph, Datasource Jeppesen
            # 1200 Version - data cycle 2112, build 20211207, metadata NavXP1200. Copyright (c) 2021 Navigraph, Datasource Jeppesen
            # re = "^([\d]{4}) Version - data cycle ([\d]{4}), build ([\d]{8}), metadata NavXP1200.(.*)"
            m = re.match(KEY_HEADER, line)
            if m is not None:
                logger.info(f":checkFile: file {os.path.basename(filename)}: Version {m[1]}, AIRAC {m[2]}, {m[5].strip()}.")
                return [file, (m[1],m[2],m[3],m[4],m[5])]

            line = file.readline()
            line.strip()

        logger.warning(f":checkFile: could not find header in {filename}")
        return [False, []]

    def loadFixes(self):
        """
        Loads X-Plane fixes database.
        """
        startLen = len(self.vert_dict.keys())
        count = 0
        filename = os.path.join(self.basename, "earth_fix.dat")
        ret = self.checkFile(filename)
        if not ret[0]:
            return [False, "XPAerospace::Fixes could not find header"]

        file = ret[0]
        v_format, v_airac, v_build, v_version, v_coypright = ret[1]

        if v_format == "1101":
            self.setAiracCycle(v_airac)
            line = file.readline()
            line.strip()

            while line:
                if line == "":
                    pass
                elif re.match("^I", line, flags=0):
                    pass
                elif re.match("^99", line, flags=0):
                    pass
                else:
                    args = line.split()      # 46.646819444 -123.722388889  AAYRR KSEA K1 4530263
                    if len(args) >= 6:       # name, region, airport, lat, lon, waypoint-type (ARINC 424)
                        lat = float(args[0])
                        lon = float(args[1])
                        self.add_vertex(Fix(args[2], args[4], args[3], lat, lon, " ".join(args[5:])))
                        count += 1

                    else:
                        if len(line) > 1:
                            logger.warning(":loadFixes: invalid fix data %s.", line)

                line = file.readline()
                line.strip()

            file.close()
        elif v_format == "1200":
            self.setAiracCycle(v_airac)
            line = file.readline()
            line.strip()

            while line:
                if line == "":
                    pass
                elif re.match("^I", line, flags=0):
                    pass
                elif re.match("^99", line, flags=0):
                    pass
                else:
                    args = line.split()      # 46.646819444 -123.722388889  AAYRR KSEA K1 4530263
                    if len(args) >= 6:       # name, region, airport, lat, lon, waypoint-type (ARINC 424)
                        lat = float(args[0])
                        lon = float(args[1])
                        self.add_vertex(Fix(args[2], args[4], args[3], lat, lon, args[5], " ".join(args[6:])))
                        count += 1

                    else:
                        if len(line) > 1:
                            logger.warning(":loadFixes: invalid fix data %s.", line)

                line = file.readline()
                line.strip()

            file.close()
        else:
            logger.warning(f":loadFixes: Fixes: unknown format {v_format}")
            return [False, "XPAerospace::Fixes unknown format"]

        logger.debug(":loadFixes: %d/%d fixes loaded.", len(self.vert_dict.keys()) - startLen, count)
        return [True, "XPAerospace::Fixes loaded"]


    def loadNavaids(self):
        """
        Loads X-Plane navigation aids database. Additional data (frequencies, etc.) is not loaded.
        """
        startLen = len(self.vert_dict.keys())
        count = 0
        filename = os.path.join(self.basename, "earth_nav.dat")
        ret = self.checkFile(filename)
        if not ret[0]:
            return [False, "XPAerospace::Navaids could not find header"]

        file = ret[0]
        v_format, v_airac, v_build, v_version, v_coypright = ret[1]

        if v_format == "1150" or v_format == "1200":
            self.setAiracCycle(v_airac)
            line = file.readline()
            line.strip()

            while line:
                if line == "":
                    pass
                elif re.match("^99", line, flags=0):
                    pass
                else:
                    args = line.split()
                    if len(args) > 10:
                        count += 1
                        lineCode = int(args[0])
                        name = " ".join(args[11:])

                        lat = float(args[1])
                        lon = float(args[2])
                        alt = float(args[3])

                        if lineCode == NAVAIDS["NDB"]:
                            # 2  47.632522222 -122.389516667 0      362    25      0.000   BF  ENRT K1 NOLLA/KBFI LMM RW13R NDB
                            # ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, name
                            self.add_vertex(NDB(ident=args[7], region=args[9], airport=args[8], lat=lat, lon=lon, elev=alt, freq=args[4], ndb_class=args[5], ndb_ident=args[6], name=" ".join(args[10:])))
                        elif lineCode == NAVAIDS["VOR"]:
                            # 3  47.435372222 -122.309616667 0    11680   130     19.000  SEA  ENRT K1 SEATTLE VORTAC
                            # ident, region, airport, lat, lon, elev, freq, vor_class, vor_ident, name
                            self.add_vertex(VOR(ident=args[7], region=args[9], airport=args[8], lat=lat, lon=lon, elev=alt, freq=args[4], ndb_class=args[5], ndb_ident=args[6], name=" ".join(args[10:])))
                        elif lineCode in (NAVAIDS["ILSLOC"], NAVAIDS["LOCLOC"]):
                            # 4  47.428408333 -122.308063889 425    11030  25  59220.343 ISNQ  KSEA K1 16L ILS-cat-III
                            # ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, runway, name
                            self.add_vertex(LOC(ident=args[7], region=args[9], airport=args[8], lat=lat, lon=lon, elev=alt, freq=args[4], ndb_class=args[5], ndb_ident=args[6], runway=args[10], name=" ".join(args[11:])))
                        elif lineCode == NAVAIDS["GS"]:
                            # 6 47.460816667 -122.309394444 425    11030 25 300180.343 ISNQ  KSEA K1 16L GS
                            # ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, runway, name
                            self.add_vertex(GS(ident=args[7], region=args[9], airport=args[8], lat=lat, lon=lon, elev=alt, freq=args[4], ndb_class=args[5], ndb_ident=args[6], runway=args[10], name=" ".join(args[11:])))
                        elif lineCode in (NAVAIDS["OM"], NAVAIDS["MM"], NAVAIDS["IM"]):
                            # ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, name
                            inv_map = {v: k for k, v in NAVAIDS.items()}
                            name = inv_map[lineCode]
                            self.add_vertex(MB(args[7], args[9], args[8], lat, lon, alt, args[4], args[5], args[6], args[10], name))  # " ".join(args[11:])))
                        elif lineCode in (NAVAIDS["DME"], NAVAIDS["DMESA"]):
                            # 47.434333333 -122.306300000 369    11030 25 0.000 ISNQ  KSEA K1 SEATTLE-TACOMA INTL DME-ILS
                            # ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, name
                            self.add_vertex(DME(ident=args[7], region=args[9], airport=args[8], lat=lat, lon=lon, elev=alt, freq=args[4], ndb_class=args[5], ndb_ident=args[6], name=" ".join(args[10:])))
                        elif lineCode == NAVAIDS["FPAP"]:
                            # 14  47.437969722 -122.311211111 429    61010 0.0 180.339 R16CY KSEA K1 16C LPV
                            # ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, runway, name
                            self.add_vertex(FPAP(ident=args[7], region=args[9], airport=args[8], lat=lat, lon=lon, elev=alt, freq=args[4], ndb_class=args[5], ndb_ident=args[6], runway=args[10], name=" ".join(args[11:])))
                        elif lineCode == NAVAIDS["GLS"]:
                            #
                            # ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, runway, name
                            self.add_vertex(GLS(ident=args[7], region=args[9], airport=args[8], lat=lat, lon=lon, elev=alt, freq=args[4], ndb_class=args[5], ndb_ident=args[6], runway=args[10], name=" ".join(args[11:])))
                        elif lineCode == NAVAIDS["LTPFTP"]:
                            # 16 47.463809028 -122.310985000 429    61010  56.6 300180.339 R16CY KSEA K1 16C WAAS
                            # ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, runway, name
                            self.add_vertex(LTPFTP(ident=args[7], region=args[9], airport=args[8], lat=lat, lon=lon, elev=alt, freq=args[4], ndb_class=args[5], ndb_ident=args[6], runway=args[10], name=" ".join(args[11:])))
                        else:
                            count -= 1
                            logger.warning(":loadNavaids: invalid navaid code %d.", lineCode)
                    else:
                        if len(line) > 1:
                            logger.warning(":loadNavaids: invalid navaid data %s.", line)


                line = file.readline()
                line.strip()
        else:
            logger.warning(f":loadNavaids: Navaids: unknown format {v_format}")
            return [False, "XPAerospace::Navaids unknown format"]

        file.close()

        logger.debug(":loadNavaids: %d/%d navaids loaded.", len(self.vert_dict.keys()) - startLen, count)
        return [True, "XPAerospace::Navaids loaded"]


    def createIndex(self):
        """
        Reverse index of fixes and navaids.
        """
        if self._cached_vectex_ids is None:
            ss = time.perf_counter()
            self._cached_vectex_ids = {}
            self._cached_vectex_idents = {}
            self._cached_vectex_ids["Fix"] = 0
            self._cached_vectex_ids["VHF"] = 0
            self._cached_vectex_ids["IDENT"] = 0
            for v in self.vert_dict.keys():
                a = SignificantPoint.parseId(ident=v)
                if not a[CPIDENT.REGION] in self._cached_vectex_ids.keys():
                    self._cached_vectex_ids[a[CPIDENT.REGION]] = {}
                if not a[CPIDENT.IDENT] in self._cached_vectex_ids[a[CPIDENT.REGION]].keys():
                    self._cached_vectex_ids[a[CPIDENT.REGION]][a[CPIDENT.IDENT]] = {}
                if a[CPIDENT.POINTTYPE] == "Fix":
                    self._cached_vectex_ids[a[CPIDENT.REGION]][a[CPIDENT.IDENT]]["Fix"] = []
                    self._cached_vectex_ids[a[CPIDENT.REGION]][a[CPIDENT.IDENT]]["Fix"].append(v)
                    self._cached_vectex_ids["Fix"] = self._cached_vectex_ids["Fix"] + 1
                else:
                    self._cached_vectex_ids[a[CPIDENT.REGION]][a[CPIDENT.IDENT]]["VHF"] = []
                    self._cached_vectex_ids[a[CPIDENT.REGION]][a[CPIDENT.IDENT]]["VHF"].append(v)
                    self._cached_vectex_ids["VHF"] = self._cached_vectex_ids["VHF"] + 1

                if not a[CPIDENT.IDENT] in self._cached_vectex_idents.keys():
                    self._cached_vectex_idents[a[CPIDENT.IDENT]] = []
                self._cached_vectex_idents[a[CPIDENT.IDENT]].append(v)

            logger.debug(f":createIndex: created ({time.perf_counter() - ss:f} sec).")


    def dropIndex(self):
        """
        Drops reverse index of fixes and navaids.

        :returns:   { description_of_the_return_value }
        :rtype:     { return_type_description }
        """
        logger.debug(":dropIndex: %d fixes, %d navaids" % (self._cached_vectex_ids["Fix"], self._cached_vectex_ids["VHF"]))
        self._cached_vectex_ids = None
        self._cached_vectex_idents = None
        logger.debug(":dropIndex: done")


    def findSignificantPoint(self, region, ident, navtypeid):
        """
        Find fix or navaid from region, identifier, and navigation aid "gross" type.

        :param      region:     The region
        :type       region:     { type_description }
        :param      ident:      The identifier
        :type       ident:      { type_description }
        :param      navtypeid:  The navtypeid
        :type       navtypeid:  { type_description }

        :returns:   { description_of_the_return_value }
        :rtype:     { return_type_description }
        """
        self.createIndex()
        if region in self._cached_vectex_ids:
            if ident in self._cached_vectex_ids[region]:
                i = self._cached_vectex_ids[region][ident]["Fix"] if int(navtypeid) == 11 else self._cached_vectex_ids[region][ident]["VHF"]
                return self.get_vertex(i[0])
        return None


    def getSignificantPoint(self, k):
        """
        Finds terminal, navaid, or fix its identifier, returns a Vertex or None.
        """
        if self.redis is not None:
            prevdb = self.redis.client_info()["db"]
            self.redis.select(REDIS_DB.REF.value)
            kr = key_path(REDIS_PREFIX.AIRSPACE_WAYPOINTS.value, k)
            ret = self.redis.json().get(kr)
            self.redis.select(prevdb)
            if ret is not None:
                # logger.debug(f":getSignificantPoint: found {kr}")
                return FeatureWithProps.new(ret)
            logger.warning(f":getSignificantPoint:  {kr} not found")
            return None
        else:
            return self.get_vertex(k)


    def findSignificantPointByIdent(self, ident):
        """
        Finds terminal, navaid, or fix its identifier, returns an array of Vertex ids.
        """
        if self.redis is not None:
            prevdb = self.redis.client_info()["db"]
            self.redis.select(REDIS_DB.REF.value)

            k = key_path(REDIS_PREFIX.AIRSPACE_WAYPOINTS_INDEX.value, ident)
            ret = self.redis.smembers(k)
            self.redis.select(prevdb)
            # logger.debug(f":findSignificantPointByIdent: {k}=>{ret}..")
            return [] if ret is None else [k.decode("UTF-8") for k in ret]
        else:
            self.createIndex()
            if ident in self._cached_vectex_idents:
                return self._cached_vectex_idents[ident]
        return []
        # s = region + ":" + ident + (":Fix" if int(navtypeid) == 11 else "") + ":"
        # candidates = [key for key in self.vert_dict.keys() if key.startswith(s)]
        # if len(candidates) > 0:
        #     # if len(candidates) > 1:
        #     #    logger.warning(":findSignificantPoint: %d matches on '%s': %s" % (len(candidates), s, candidates))
        #     return self.vert_dict[candidates[0]]
        # logger.debug(":findSignificantPoint: '%s' not found (%s, %s, %s)" % (s, region, ident, navtypeid))
        # return None


    def findClosestSignificantPoint(self, reference, vertlist):
        """
        Finds closest navigation aid or fix to reference vertex.
        """
        closest = None
        refvtx = self.get_vertex(reference)
        dist = inf
        for v in vertlist:
            if self.redis is not None:
                prevdb = self.redis.client_info()["db"]
                self.redis.select(REDIS_DB.REF.value)
                d = self.redis.geodist(REDIS_PREFIX.AIRSPACE_WAYPOINTS_GEO_INDEX.value, reference, v)
                logger.debug(f":findClosestSignificantPoint:Redis: {v}: {d}")
                self.redis.select(prevdb)
            else:
                vtx = self.get_vertex(v)
                d = distance(refvtx, vtx)
            if d < dist:
                dist = d
                closest = v
        return [closest, dist]


    def distance(self, reference, v):
        """
        Finds distance between two vertices.
        """
        refvtx = self.get_vertex(reference)

        if self.redis is not None:
            prevdb = self.redis.client_info()["db"]
            self.redis.select(REDIS_DB.REF.value)
            d = self.redis.geodist(REDIS_PREFIX.AIRSPACE_WAYPOINTS_GEO_INDEX.value, reference, v)
            self.redis.select(prevdb)
        else:
            vtx = self.get_vertex(v)
            d = distance(refvtx, vtx)
        return d


    def loadAirwaySegments(self):
        """
        Loads airway segments from X-Plane segments database.
        """
        # 0     1  2  3     4  5
        # ABILO LG 11 PERIM LG 11 F 1   0   0 L53
        #   LAS K2  3 SUVIE K2 11 N 2 180 450 J100-J9
        #
        #
        filename = os.path.join(self.basename, "earth_awy.dat")
        ret = self.checkFile(filename)
        if not ret[0]:
            return [False, "XPAerospace::AirwaySegments could not find header"]

        file = ret[0]
        v_format, v_airac, v_build, v_version, v_coypright = ret[1]

        if v_format == "1100":
            self.setAiracCycle(v_airac)
            line = file.readline()
            line.strip()
            count = 0
            self.createIndex()  # special to locate fixes for airways

            while line:
                if line == "":
                    pass
                elif re.match("^I", line, flags=0):
                    pass
                elif re.match("^99", line, flags=0):
                    pass
                else:
                    args = line.split()
                    if len(args) == 11:  # names, start, end, direction, lowhigh, fl_floor, fl_ceil
                        src = self.findSignificantPoint(region=args[1], ident=args[0], navtypeid=args[2])
                        if src:
                            dst = self.findSignificantPoint(region=args[4], ident=args[3], navtypeid=args[5])
                            if dst:
                                if args[6] == DIRECTION["FORWARD"]:
                                    self.add_edge(AirwaySegment(args[10], src, dst, True, args[7], args[8], args[9]))
                                elif args[6] == DIRECTION["BACKWARD"]:
                                    self.add_edge(AirwaySegment(args[10], dst, src, True, args[7], args[8], args[9]))
                                else:
                                    self.add_edge(AirwaySegment(args[10], src, dst, False, args[7], args[8], args[9]))
                                count += 1
                                if count % 10000 == 0:
                                    logger.debug(":loadAirwaySegments: %d segments loaded.", count)
                            else:
                                logger.debug("could not find end of segment %s, %s, %s, %s", args[10], args[4], args[3], args[5])
                        else:
                            logger.debug("could not find start of segment %s, %s, %s, %s", args[10], args[0], args[1], args[2])
                    else:
                        if len(line) > 1:
                            logger.warning(":loadAirwaySegments: invalid segment data %s (%d).", line, count)

                line = file.readline()
                line.strip()

            file.close()

            self.dropIndex()
            self.airways_loaded = True
        else:
            logger.warning(f":loadAirwaySegments: Airway segments: unknown format {v_format}")
            return [False, "XPAerospace::AirwaySegments unknown format"]

        logger.debug(":loadAirwaySegments: %d segments loaded.", len(self.edges_arr))
        return [True, "XPAerospace::AirwaySegments loaded"]


    def loadHolds(self):
        """
        Loads holding positions and patterns from X-Plane holds databaes.
        """
        lonmin, lonmax = (50, 53)
        latmin, latmax = (23, 27)
        def inBbox(p):
            if LOCAL_HOLDS_ONLY:
                lat = p["geometry"]["coordinates"][1]
                lon = p["geometry"]["coordinates"][0]
                return (lat > latmin) and (lat < latmax) and (lon > lonmin) and (lon < lonmax)
            return True

        filename = os.path.join(self.basename, "earth_hold.dat")
        ret = self.checkFile(filename)
        if not ret[0]:
            return [False, "XPAerospace::Holds could not find header"]

        file = ret[0]
        v_format, v_airac, v_build, v_version, v_coypright = ret[1]

        if v_format == "1140":
            self.setAiracCycle(v_airac)
            line = file.readline()
            line.strip()
            count = 0
            self.createIndex()  # special to locate fixes for airways

            while line:
                if line == "":
                    pass
                elif re.match("^I", line, flags=0):
                    pass
                elif re.match("^99", line, flags=0):
                    pass
                else:
                    # LBU    ED      ENRT     3        178.0     1.0       0.0         L        5000    0       0
                    # ident, region, airport, fixtype, incourse, leg_time, leg_length, turndir, minalt, maxalt, maxspeed
                    # 0      1       2        3        4         5         6           7        8       9       10
                    args = line.split()
                    if len(args) >= 6:
                        fix = self.findSignificantPoint(region=args[1], ident=args[0], navtypeid=args[3])
                        if fix is None:
                            logger.warning(":loadHolds: fix not found %s.", line)
                        else:
                            if inBbox(fix):
                                hid = SignificantPoint.mkId(region=args[1], airport=args[2], ident=args[0], pointtype="HLD")
                                self.holds[hid] = Hold(fix=fix, altmin=float(args[8]), altmax=float(args[9]),
                                                       course=float(args[4]), turn=args[7], leg_time=float(args[5]), leg_length=float(args[6]), speed=float(args[10]))
                    else:
                        if len(line) > 1:
                            logger.warning(":loadHolds: invalid fix data %s.", line)

                line = file.readline()
                line.strip()

            file.close()
        else:
            logger.warning(f":loadHolds: Holds: unknown format {v_format}")
            return [False, "XPAerospace::Holds unknown format"]

        # logger.info(":loadHolds: %d holds loaded.", len(self.holds))
        logger.debug(f":loadHolds: {len(self.holds)} holds loaded.")
        # logger.debug(f":loadHolds: {self.holds.keys()}")
        return [True, "XPAerospace::Holds loaded"]


    def loadAirspaces(self):
        """
        Load all airspaces from Little Navmap.
        {
        "type": "Feature",
        "geometry": {
        "type": "Polygon",
        "coordinates": [ [ [0, 0], .. ,[0, 0] ] ]
        },
        "properties": {
        "boundary_id": 29386,
        "file_id": 1,
        "type": "FIR",
        "name": "HONIARA",
        "description": null,
        "restrictive_designation": null,
        "restrictive_type": null,
        "multiple_code": "",
        "time_code": "U",
        "com_type": "CTR",
        "com_frequency": 118100,
        "com_name": "HONIARA",
        "min_altitude_type": "MSL",
        "max_altitude_type": "UL",
        "min_altitude": 0,
        "max_altitude": 100000,
        "max_lonx": 166.875,
        "max_laty": -4.833333492279053,
        "min_lonx": 155,
        "min_laty": -14
        }
        }
        List of values:
        --------------
        type: ["AL","C","CA","CB","CC","CD","CE","CF","CG","CN","DA","FIR","GCA","M","MCTR","P","R","RD","T","TR","TRSA","UIR","W"]
        restrictive_type: [null,"A","C","D","M","P","R","T","W"]
        multiple_code: [null,"A", .. ,"Z"]
        time_code: [null,"C","H","N","U"]
        comm_type: [null,"CTR"]

        """
        airspaces = files('data.airspaces').joinpath('boundaries.geojson').read_text()
        fc = json.loads(airspaces)
        for f in fc["features"]:
            props = f["properties"]
            r = Restriction(altmin=props["min_altitude"],
                            altmax=props["max_altitude"])
            r.altmin_type = props["min_altitude_type"]
            r.altmax_type = props["max_altitude_type"]
            ca = ControlledAirspace(name=props["name"],
                                    region="",
                                    airspace_class="",
                                    restriction=r,
                                    area=f["geometry"])
            for p in props:
                ca.setProp(p, props[p])
            ca.setId(props["boundary_id"])
            self.airspaces[props["boundary_id"]] = ca

        logger.debug(f":loadAirspaces: loaded {len(self.airspaces)} boundaries")

        return [True, "XPAerospace::loadAirspaces aispace loaded"]
