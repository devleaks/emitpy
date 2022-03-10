# Airspace Utility Classes
#
import os.path
import re
import logging
import time
from math import inf
from turfpy.measurement import distance

from .airspace import Airspace, Apt, Fix, ControlledPoint, AirwaySegment, CPIDENT
from .airspace import NDB, VOR, LOC, MB, DME, GS, FPAP, GLS, LTPFTP, Hold

from ..parameters import DATA_DIR

SYSTEM_DIRECTORY = os.path.join(DATA_DIR, "x-plane")

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("XPAirspace")

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

##########################
#
# A I R   S P A C E   D A T A   I S S U E D   F R O M   X -P L A N E
# (Alternatives are Navigraph, ARIAC 424, etc.)
#
class XPAirspace(Airspace):

    def __init__(self, bbox=None):
        Airspace.__init__(self, bbox)
        self.basename = os.path.join(SYSTEM_DIRECTORY, "Resources", "default data")
        self._cached_vectex_ids = None
        self._cached_vectex_idents = None
        self.simairspacetype = "X-Plane"


    def loadAirports(self):
        # From https://www.partow.net/miscellaneous/airportdatabase/index.html#Downloads
        startLen = len(self.vert_dict.keys())
        count = 0
        filename = os.path.join(SYSTEM_DIRECTORY, "GlobalAirportDatabase.txt")
        file = open(filename, "r")
        logger.info(":loadAirports: from %s.", filename)
        line = file.readline()
        line.strip()

        while line:
            # EBBR:BRU:BRUSSELS NATL:BRUSSELS:BELGIUM:050:054:008:N:004:029:055:E:00057:50.902:4.499
            args = line.split(":")
            if len(args) == 16:       # name, lat, lon, alt, IATA, name, country, city
                lat = float(args[14])
                lon = float(args[15])
                alt = int(args[13])
                if lat != 0.0 or lon != 0.0:
                    self.add_vertex(Apt(args[0], lat, lon, alt, args[1], args[2], args[3], args[4]))
            else:
                logger.warning(":loadAirports: invalid airport data %s.", line)
            line = file.readline()
            line.strip()
            count += 1

        file.close()

        logger.debug(":loadAirports: %d/%d airports loaded.", len(self.vert_dict.keys()) - startLen, count)
        return [True, "XPXPAirspace::Airport loaded"]


    def loadFixes(self):
        startLen = len(self.vert_dict.keys())
        count = 0
        filename = os.path.join(self.basename, "earth_fix.dat")
        file = open(filename, "r")
        line = file.readline()
        line.strip()

        while line:
            if line == "":
                pass
            if re.match("^I", line, flags=0):
                pass
            elif re.match("^1101 Version", line, flags=0):
                logger.info(line.strip())
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

        logger.debug(":loadFixes: %d/%d fixes loaded.", len(self.vert_dict.keys()) - startLen, count)
        return [True, "XPXPAirspace::Fixes loaded"]


    def loadNavaids(self):
        startLen = len(self.vert_dict.keys())
        count = 0
        filename = os.path.join(self.basename, "earth_nav.dat")
        file = open(filename, "r")
        line = file.readline()
        line.strip()

        while line:
            if line == "":
                pass
            if re.match("^I", line, flags=0):
                pass
            elif re.match("^1150 Version", line, flags=0):
                logger.info(line.strip())
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

        file.close()

        logger.debug(":loadNavaids: %d/%d navaids loaded.", len(self.vert_dict.keys()) - startLen, count)
        return [True, "XPXPAirspace::Navaids loaded"]


    def createIndex(self):
        if self._cached_vectex_ids is None:
            ss = time.perf_counter()
            self._cached_vectex_ids = {}
            self._cached_vectex_idents = {}
            self._cached_vectex_ids["Fix"] = 0
            self._cached_vectex_ids["VHF"] = 0
            self._cached_vectex_ids["IDENT"] = 0
            for v in self.vert_dict.keys():
                a = ControlledPoint.parseId(ident=v)
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
        logger.debug(":dropIndex: %d fixes, %d navaids" % (self._cached_vectex_ids["Fix"], self._cached_vectex_ids["VHF"]))
        self._cached_vectex_ids = None
        self._cached_vectex_idents = None
        logger.debug(":dropIndex: done")


    def findControlledPoint(self, region, ident, navtypeid):
        self.createIndex()
        if region in self._cached_vectex_ids:
            if ident in self._cached_vectex_ids[region]:
                i = self._cached_vectex_ids[region][ident]["Fix"] if int(navtypeid) == 11 else self._cached_vectex_ids[region][ident]["VHF"]
                return self.vert_dict[i[0]]
        return None


    def findControlledPointByName(self, ident):
        self.createIndex()
        if ident in self._cached_vectex_idents:
            return self._cached_vectex_idents[ident]
        return []

        """
        s = region + ":" + ident + (":Fix" if int(navtypeid) == 11 else "") + ":"
        candidates = [key for key in self.vert_dict.keys() if key.startswith(s)]

        if len(candidates) > 0:
            # if len(candidates) > 1:
            #    logger.warning(":findControlledPoint: %d matches on '%s': %s" % (len(candidates), s, candidates))
            return self.vert_dict[candidates[0]]

        logger.debug(":findControlledPoint: '%s' not found (%s, %s, %s)" % (s, region, ident, navtypeid))
        return None
        """

    def findClosestControlledPoint(self, reference, vertlist):
        closest = None
        refvtx = self.get_vertex(reference)
        dist = inf
        for v in vertlist:
            vtx = self.get_vertex(v)
            d = distance(refvtx, vtx)
            if d < dist:
                dist = d
                closest = v
        return [closest, dist]


    def loadAirwaySegments(self):
        # 0     1  2  3     4  5
        # ABILO LG 11 PERIM LG 11 F 1   0   0 L53
        #   LAS K2  3 SUVIE K2 11 N 2 180 450 J100-J9
        #
        #
        filename = os.path.join(self.basename, "earth_awy.dat")
        file = open(filename, "r")
        line = file.readline()
        line.strip()
        count = 0
        self.createIndex()  # special to located fixes for airways
        while line:
            if line == "":
                pass
            if re.match("^I", line, flags=0):
                pass
            elif re.match("^1100 Version", line, flags=0):
                logger.info(line.strip())
            elif re.match("^99", line, flags=0):
                pass
            else:
                args = line.split()
                if len(args) == 11:  # names, start, end, direction, lowhigh, fl_floor, fl_ceil
                    src = self.findControlledPoint(region=args[1], ident=args[0], navtypeid=args[2])
                    if src:
                        dst = self.findControlledPoint(region=args[4], ident=args[3], navtypeid=args[5])
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

        logger.debug(":loadAirwaySegments: %d segments loaded.", len(self.edges_arr))
        return [True, "XPXPAirspace::AirwaySegments loaded"]

    """
    {
      "type": "Feature",
      "properties": {},
      "geometry": {
        "type": "Polygon",
        "coordinates": [
          [
            [
              48.0,
              22.0
            ],
            [
              55.0,
              22.0
            ],
            [
              55.0,
              28.0
            ],
            [
              48.0,
              28.0
            ],
            [
              48.0,
              22.0
            ]
          ]
        ]
      }
    }"""

    def loadHolds(self):
        filename = os.path.join(self.basename, "earth_hold.dat")
        file = open(filename, "r")
        line = file.readline()
        line.strip()

        lonmin, lonmax = (50, 53)
        latmin, latmax = (23, 27)
        def inBbox(p):
            lat = p["geometry"]["coordinates"][1]
            lon = p["geometry"]["coordinates"][0]
            return (lat > latmin) and (lat < latmax) and (lon > lonmin) and (lon < lonmax)

        while line:
            if line == "":
                pass
            if re.match("^I", line, flags=0):
                pass
            elif re.match("^1140 Version", line, flags=0):
                logger.info(line.strip())
            elif re.match("^99", line, flags=0):
                pass
            else:
                # LBU    ED      ENRT     3        178.0     1.0       0.0         L        5000    0       0
                # ident, region, airport, fixtype, incourse, leg_time, leg_length, turndir, minalt, maxalt, maxspeed
                # 0      1       2        3        4         5         6           7        8       9       10
                args = line.split()
                if len(args) >= 6:
                    fix = self.findControlledPoint(region=args[1], ident=args[0], navtypeid=args[3])
                    if fix is None:
                        logger.warning(":loadHolds: fix not found %s.", line)
                    else:
                        if inBbox(fix):
                            hid = ControlledPoint.mkId(region=args[1], airport=args[2], ident=args[0], pointtype="HLD")
                            self.holds[hid] = Hold(fix=fix, altmin=float(args[8]), altmax=float(args[9]),
                                                   course=float(args[4]), turn=args[7], leg_time=float(args[5]), leg_length=float(args[6]), speed=float(args[10]))
                else:
                    if len(line) > 1:
                        logger.warning(":loadHolds: invalid fix data %s.", line)

            line = file.readline()
            line.strip()

        file.close()

        # logger.info(":loadHolds: %d holds loaded.", len(self.holds))
        logger.debug(f":loadHolds: {len(self.holds)} holds loaded. {self.holds.keys()}")
        return [True, "XPXPAirspace::Holds loaded"]


