# Airport Utility Class
# Airport information container: name, taxi routes, runways, ramps, etc.
#
import os.path
import re
import logging

from graph import Vertex, Edge, Graph, Route
from geo import Point, Line, Polygon, BoundingBox, distance, nearestPointToLines, destination, pointInPolygon

SYSTEM_DIRECTORY = os.path.join("..", "data", "x-plane")

POINT_TYPES = {
    "FIX": 11,
    "ENROUTENDB": 2,
    "VHF": 3
}

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


class Navpoint(Vertex):

    def __init__(self, ident, region, airport, lat, lon, navtype):
        Vertex.__init__(self, Navpoint.mkId(region, airport, ident, navtype), Point(lat, lon), "both")
        self.ident = ident
        self.region = region
        self.airport = airport
        self.navtype = navtype

    def getId(self):
        return self.navtype+":"+self.region+":"+self.airport+":"+self.ident

    @staticmethod
    def mkId(region, airport, ident, navtype):
        return navtype+":"+region+":"+airport+":"+ident


class Airport(Navpoint):

    def __init__(self, name, lat, lon, iata, longname, country, city):
        Navpoint.__init__(self, name, "WORLD", name, lat, lon, "APT")
        self.iata = iata
        self.country = country
        self.city = city
        self.name = longname


class Fix(Navpoint):
    # 46.646819444 -123.722388889  AAYRR KSEA K1 4530263

    def __init__(self, name, region, airport, lat, lon, waypoint):
        Navpoint.__init__(self, name, region, airport, lat, lon, "FIX")
        self.waypoint = waypoint


class NDB(Navpoint):  # 2

    def __init__(self, ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, name):
        Navpoint.__init__(self, ident, region, airport, lat, lon, "NDB")
        self.name = name


class VOR(Navpoint):  # 3

    def __init__(self, ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, name):
        Navpoint.__init__(self, ident, region, airport, lat, lon, "VOR")
        self.name = name


class LOC(Navpoint):  # 4,5

    def __init__(self, ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, runway, name):
        Navpoint.__init__(self, ident, region, airport, lat, lon, "LOC")
        self.runway = runway
        self.name = name


class GS(Navpoint):  # 6

    def __init__(self, ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, runway, name):
        Navpoint.__init__(self, ident, region, airport, lat, lon, "GS")
        self.runway = runway
        self.name = name


class MB(Navpoint):  # 7,8,9

    def __init__(self, ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, runway, name, marker):
        inv_map = {v: k for k, v in NAVAIDS.items()}
        Navpoint.__init__(self, ident, region, airport, lat, lon, inv_map[marker])
        self.runway = runway
        self.name = name


class DME(Navpoint):  # 12,13

    def __init__(self, ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, name):
        Navpoint.__init__(self, ident, region, airport, lat, lon, "DME")
        self.name = name


class FPAP(Navpoint):  # 14

    def __init__(self, ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, runway, name):
        Navpoint.__init__(self, ident, region, airport, lat, lon, "FPAP")
        self.runway = runway
        self.name = name


class GLS(Navpoint):  # 16

    def __init__(self, ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, runway, name):
        Navpoint.__init__(self, ident, region, airport, lat, lon, "GLS")
        self.runway = runway
        self.name = name


class LTPFTP(Navpoint):  # 16

    def __init__(self, ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, runway, name):
        Navpoint.__init__(self, ident, region, airport, lat, lon, "LTPFTP")
        self.runway = runway
        self.name = name


class AirwaySegment(Edge):

    def __init__(self, names, start, end, direction, lowhigh, fl_floor, fl_ceil):
        cost = distance(start, end)
        Edge.__init__(self, start, end, cost, direction, "airway", names)  # (self, src, dst, cost, direction, usage, name)
        self.names = names.split("-")
        self.direction = direction
        self.lowhigh = lowhigh
        self.fl_floor = fl_floor
        self.fl_ceil = fl_ceil



class XPAirspace(Graph):
    # Airspace data

    def __init__(self, bbox=None):
        Graph.__init__(self)
        self.navpoints = {}
        self.loaded = False
        self.basename = os.path.join(SYSTEM_DIRECTORY, "Resources", "default data")


    def add_navpoint(self, navpoint):
        self.vert_dict[navpoint.getId()] = navpoint

        # build kind of dict index
        if navpoint.navtype not in self.navpoints.keys():
            self.navpoints[navpoint.navtype] = {}
        ty = self.navpoints[navpoint.navtype]
        if navpoint.region not in ty.keys():
            ty[navpoint.region] = {}
        if navpoint.ident not in ty[navpoint.region].keys():
            ty[navpoint.region][navpoint.ident] = []
        ty[navpoint.region][navpoint.ident].append(navpoint)


    def get_navpoint(self, region, airport, ident, navtype):
        return self.get_vertex(Navpoint.mkId(region, airport, ident, navtype))


    def try_navpoint(self, region, ident, nt):
        navtype = int(nt)
        if navtype == -1:
            if "APT" in self.navpoints.keys():
                ty = self.navpoints["APT"]
                if region in ty.keys():
                    if ident in ty[region]:
                        if len(ty[region][ident]) == 1:
                            return ty[region][ident][0]
                        for r in ty[region][ident]:  # send back the first enroute fix. @todo
                            if r.airport == "ENRT":
                                return r
                        logging.warning("Airspace::get_navpoint: abiguous fix %s, %s", region, ident)
                        return None
        elif navtype == 11:
            if "FIX" in self.navpoints.keys():
                ty = self.navpoints["FIX"]
                if region in ty.keys():
                    if ident in ty[region]:
                        if len(ty[region][ident]) == 1:
                            return ty[region][ident][0]
                        for r in ty[region][ident]:  # send back the first enroute fix. @todo
                            if r.airport == "ENRT":
                                return r
                        logging.warning("Airspace::get_navpoint: abiguous fix %s, %s", region, ident)
                        return None
        elif navtype == 2:  # En route NDB
            if "NDB" in self.navpoints.keys():
                ty = self.navpoints["NDB"]
                if region in ty.keys():
                    if ident in ty[region]:
                        if len(ty[region][ident]) == 1:
                            return ty[region][ident][0]
                        for r in ty[region][ident]:  # send back the first enroute fix. ambiguity is probably linked to high and low routes (same name)
                            if r.airport == "ENRT":
                                return r
                        logging.warning("Airspace::get_navpoint: abiguous ndb %s, %s", region, ident)
                        return None
        elif navtype == 3:  # VHF nav aid
            if "VOR" in self.navpoints.keys():
                ty = self.navpoints["VOR"]
                if region in ty.keys():
                    if ident in ty[region]:
                        if len(ty[region][ident]) == 1:
                            return ty[region][ident][0]
                        logging.warning("Airspace::get_navpoint: abiguous vor %s, %s", region, ident)

            if "DME" in self.navpoints.keys():
                ty = self.navpoints["DME"]
                if region in ty.keys():
                    if ident in ty[region]:
                        if len(ty[region][ident]) == 1:
                            return ty[region][ident][0]
                        logging.warning("Airspace::get_navpoint: abiguous dme %s, %s", region, ident)
                        return None
        else:
            logging.warning("Airspace::get_navpoint: invalid navtype %d", navtype)

        logging.warning("Airspace::get_navpoint: not found navtype %s, %s, %s", region, ident, nt)
        return None


    def load(self):
        status = self.loadAirports()
        if not status:
            return [False, "We could not load airports."]

        status = self.loadNavaids()
        if not status:
            return [False, "We could not load navaids."]

        status = self.loadFixes()
        if not status:
            return [False, "We could not load fixes."]

        status = self.loadAirwaySegments()
        if not status:
            return [False, "We could not load airway segments."]

        return [True, "Airspace ready"]


    def loadAirports(self):
        # From https://www.partow.net/miscellaneous/airportdatabase/index.html#Downloads
        startLen = len(self.vert_dict.keys())
        count = 0
        filename = os.path.join(SYSTEM_DIRECTORY, "GlobalAirportDatabase.txt")
        file = open(filename, "r")
        line = file.readline()
        line.strip()

        while line:
            # EBBR:BRU:BRUSSELS NATL:BRUSSELS:BELGIUM:050:054:008:N:004:029:055:E:00057:50.902:4.499
            args = line.split(":")
            if len(args) == 16:       # name, lat, lon, alt, IATA, name, country, city
                if float(args[14]) != 0.0 or float(args[15]) != 0.0:
                    self.add_navpoint(Airport(args[0], args[14], args[15], args[1], args[2], args[3], args[4]))
            else:
                logging.warning("Airspace::loadAirports: invalid airport data %s.", line)
            line = file.readline()
            line.strip()
            count += 1

        file.close()

        logging.info("Airspace::loadAirports: %d/%d airports loaded.", len(self.vert_dict.keys()) - startLen, count)
        return True


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
                logging.info(line)
            elif re.match("^99", line, flags=0):
                pass
            else:
                args = line.split()      # 46.646819444 -123.722388889  AAYRR KSEA K1 4530263
                if len(args) >= 6:       # name, region, airport, lat, lon, waypoint
                    self.add_navpoint(Fix(args[2], args[4], args[3], args[0], args[1], " ".join(args[5:])))
                    count += 1

                else:
                    if len(line) > 1:
                        logging.warning("Airspace::loadFixes: invalid fix data %s.", line)

            line = file.readline()
            line.strip()

        file.close()

        logging.debug("Airspace::loadFixes: %d/%d fixes loaded.", len(self.vert_dict.keys()) - startLen, count)
        return True


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
                logging.info(line)
                pass
            elif re.match("^99", line, flags=0):
                pass
            else:
                args = line.split()
                if len(args) > 10:
                    count += 1
                    lineCode = int(args[0])
                    name = " ".join(args[11:])
                    if lineCode == NAVAIDS["NDB"]:
                        # 2  47.632522222 -122.389516667 0      362    25      0.000   BF  ENRT K1 NOLLA/KBFI LMM RW13R NDB
                        # ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, name
                        self.add_navpoint(NDB(args[7], args[9], args[8], args[1], args[2], args[3], args[4], args[5], args[6], " ".join(args[10:])))
                    elif lineCode == NAVAIDS["VOR"]:
                        # 3  47.435372222 -122.309616667 0    11680   130     19.000  SEA  ENRT K1 SEATTLE VORTAC
                        # ident, region, airport, lat, lon, elev, freq, vor_class, vor_ident, name
                        self.add_navpoint(VOR(args[7], args[9], args[8], args[1], args[2], args[3], args[4], args[5], args[6], " ".join(args[10:])))
                    elif lineCode in (NAVAIDS["ILSLOC"], NAVAIDS["LOCLOC"]):
                        # 4  47.428408333 -122.308063889 425    11030  25  59220.343 ISNQ  KSEA K1 16L ILS-cat-III
                        # ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, runway, name
                        self.add_navpoint(LOC(args[7], args[9], args[8], args[1], args[2], args[3], args[4], args[5], args[6], args[10], " ".join(args[11:])))
                    elif lineCode == NAVAIDS["GS"]:
                        # 6 47.460816667 -122.309394444 425    11030 25 300180.343 ISNQ  KSEA K1 16L GS
                        # ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, runway, name
                        self.add_navpoint(GS(args[7], args[9], args[8], args[1], args[2], args[3], args[4], args[5], args[6], args[10], " ".join(args[11:])))
                    elif lineCode in (NAVAIDS["OM"], NAVAIDS["MM"], NAVAIDS["IM"]):
                        # ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, name
                        self.add_navpoint(MB(args[7], args[9], args[8], args[1], args[2], args[3], args[4], args[5], args[6], args[10], " ".join(args[11:]), lineCode))
                    elif lineCode in (NAVAIDS["DME"], NAVAIDS["DMESA"]):
                        # 47.434333333 -122.306300000 369    11030 25 0.000 ISNQ  KSEA K1 SEATTLE-TACOMA INTL DME-ILS
                        # ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, name
                        self.add_navpoint(DME(args[7], args[9], args[8], args[1], args[2], args[3], args[4], args[5], args[6], " ".join(args[10:])))
                    elif lineCode == NAVAIDS["FPAP"]:
                        # 14  47.437969722 -122.311211111 429    61010 0.0 180.339 R16CY KSEA K1 16C LPV
                        # ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, runway, name
                        self.add_navpoint(FPAP(args[7], args[9], args[8], args[1], args[2], args[3], args[4], args[5], args[6], args[10], " ".join(args[11:])))
                    elif lineCode == NAVAIDS["GLS"]:
                        #
                        # ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, runway, name
                        self.add_navpoint(GLS(args[7], args[9], args[8], args[1], args[2], args[3], args[4], args[5], args[6], args[10], " ".join(args[11:])))
                    elif lineCode == NAVAIDS["LTPFTP"]:
                        # 16 47.463809028 -122.310985000 429    61010  56.6 300180.339 R16CY KSEA K1 16C WAAS
                        # ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, runway, name
                        self.add_navpoint(LTPFTP(args[7], args[9], args[8], args[1], args[2], args[3], args[4], args[5], args[6], args[10], " ".join(args[11:])))
                    else:
                        count -= 1
                        logging.warning("Airspace::loadNavaids: invalid navaid code %d.", lineCode)
                else:
                    if len(line) > 1:
                        logging.warning("Airspace::loadNavaids: invalid navaid data %s.", line)


            line = file.readline()
            line.strip()

        file.close()

        logging.debug("Airspace::loadNavaids: %d/%d navaids loaded.", len(self.vert_dict.keys()) - startLen, count)
        return True


    def loadAirwaySegments(self):
        # ABILO LG 11 PERIM LG 11 F 1   0   0 L53
        #   LAS K2  3 SUVIE K2 11 N 2 180 450 J100-J9
        filename = os.path.join(self.basename, "earth_awy.dat")
        file = open(filename, "r")
        line = file.readline()
        line.strip()
        count = 0
        while line:
            if line == "":
                pass
            if re.match("^I", line, flags=0):
                pass
            elif re.match("^1100 Version", line, flags=0):
                logging.info(line)
                pass
            elif re.match("^99", line, flags=0):
                pass
            else:
                args = line.split()
                if len(args) == 11:  # names, start, end, direction, lowhigh, fl_floor, fl_ceil
                    src = self.try_navpoint(args[1], args[0], args[2])
                    if src:
                        dst = self.try_navpoint(args[4], args[3], args[5])
                        if dst:
                            self.add_edge(AirwaySegment(args[10], src, dst, args[6], args[7], args[8], args[9]))
                            count += 1
                        else:
                            logging.debug("could not find end of segment %s, %s, %s, %s", args[10], args[4], args[3], args[5])
                    else:
                        logging.debug("could not find start of segment %s, %s, %s, %s", args[10], args[0], args[1], args[2])
                else:
                    if len(line) > 1:
                        logging.warning("Airspace::loadAirwaySegments: invalid segment data %s (%d).", line, count)

            line = file.readline()
            line.strip()

        file.close()

        logging.debug("Airspace::loadAirwaySegments: %d segments loaded.", len(self.edges_arr))
        return True


    def mkBbox(self, a, b, large):
        ll = Point(min(a.lat, b.lat), min(a.lon, b.lon))
        ur = Point(max(a.lat, b.lat), max(a.lon, b.lon))
        ll1 = destination(ll, 225, large)
        ur1 = destination(ur, 45, large)
        return BoundingBox(ll1, ur1)


    def mkRoute(self, src, dst):

        asrc = self.try_navpoint("WORLD", src, -1)
        if not asrc:
            return [False, "Could not find departure airport"]

        vsrc = self.findClosestVertex(asrc)
        if not vsrc[0]:
            return [False, "Could not find vertex close to departure"]

        adst = self.try_navpoint("WORLD", dst, -1)
        if not adst:
            return [False, "Could not find arrival airport"]

        vdst = self.findClosestVertex(adst)
        if not vdst[0]:
            return [False, "Could not find vertex close to arrival"]

        # We only keep vertices in a boundingbox around the flight
        self.bbox = self.mkBbox(asrc, adst, 150000)  # 150km larger...

        route = Route(self, vsrc[0], vdst[0], "", {"bbox": self.bbox})
        route.find()
        if route.found():  # second attempt may have worked
            return (True, route)

        return (False, "We could not find a route to your destination.")
