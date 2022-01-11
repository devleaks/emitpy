# Airspace Utility Classes
#
import os.path
import math
import re
import logging
logger = logging.getLogger("XPAirspace")


from .airspace import Airspace

SYSTEM_DIRECTORY = os.path.join(DATA_DIR, "x-plane")

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



##########################
#
# A I R   S P A C E
#
#
class XPAirspace(Airspace):
    # Airspace data

    def __init__(self, bbox=None):
        Graph.__init__(self, bbox)
        self.basename = os.path.join(SYSTEM_DIRECTORY, "Resources", "default data")


    def load(self):
        status = self.loadAirports()

        if not status[0]:
            return [False, status[1]]

        status = self.loadNavaids()
        if not status[0]:
            return [False, status[1]]

        status = self.loadFixes()
        if not status[0]:
            return [False, status[1]]

        status = self.loadAirwaySegments()
        if not status[0]:
            return [False, status[1]]

        return [True, "XPAirspace loaded"]


    def loadAirports(self):
        # From https://www.partow.net/miscellaneous/airportdatabase/index.html#Downloads
        startLen = len(self.vert_dict.keys())
        count = 0
        filename = os.path.join(SYSTEM_DIRECTORY, "GlobalAirportDatabase.txt")
        file = open(filename, "r")
        logging.info("XPAirspace::loadAirports: from %s.", filename)
        line = file.readline()
        line.strip()

        while line:
            # EBBR:BRU:BRUSSELS NATL:BRUSSELS:BELGIUM:050:054:008:N:004:029:055:E:00057:50.902:4.499
            args = line.split(":")
            if len(args) == 16:       # name, lat, lon, alt, IATA, name, country, city
                lat = float(args[14])
                lon = float(args[15])
                if lat != 0.0 or lon != 0.0:
                    self.add_ControlledPoint(Airport(args[0], lat, lon, args[1], args[2], args[3], args[4]))
            else:
                logging.warning("XPAirspace::loadAirports: invalid airport data %s.", line)
            line = file.readline()
            line.strip()
            count += 1

        file.close()

        logging.info("XPAirspace::loadAirports: %d/%d airports loaded.", len(self.vert_dict.keys()) - startLen, count)
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
                logging.info(line.strip())
            elif re.match("^99", line, flags=0):
                pass
            else:
                args = line.split()      # 46.646819444 -123.722388889  AAYRR KSEA K1 4530263
                if len(args) >= 6:       # name, region, airport, lat, lon, ControlledPoint
                    lat = float(args[0])
                    lon = float(args[1])
                    self.add_ControlledPoint(Fix(args[2], args[4], args[3], lat, lon, " ".join(args[5:])))
                    count += 1

                else:
                    if len(line) > 1:
                        logging.warning("XPAirspace::loadFixes: invalid fix data %s.", line)

            line = file.readline()
            line.strip()

        file.close()

        logging.debug("XPAirspace::loadFixes: %d/%d fixes loaded.", len(self.vert_dict.keys()) - startLen, count)
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
                logging.info(line.strip())
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
                        self.add_ControlledPoint(NDB(args[7], args[9], args[8], lat, lon, alt, args[4], args[5], args[6], " ".join(args[10:])))
                    elif lineCode == NAVAIDS["VOR"]:
                        # 3  47.435372222 -122.309616667 0    11680   130     19.000  SEA  ENRT K1 SEATTLE VORTAC
                        # ident, region, airport, lat, lon, elev, freq, vor_class, vor_ident, name
                        self.add_ControlledPoint(VOR(args[7], args[9], args[8], lat, lon, alt, args[4], args[5], args[6], " ".join(args[10:])))
                    elif lineCode in (NAVAIDS["ILSLOC"], NAVAIDS["LOCLOC"]):
                        # 4  47.428408333 -122.308063889 425    11030  25  59220.343 ISNQ  KSEA K1 16L ILS-cat-III
                        # ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, runway, name
                        self.add_ControlledPoint(LOC(args[7], args[9], args[8], lat, lon, alt, args[4], args[5], args[6], args[10], " ".join(args[11:])))
                    elif lineCode == NAVAIDS["GS"]:
                        # 6 47.460816667 -122.309394444 425    11030 25 300180.343 ISNQ  KSEA K1 16L GS
                        # ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, runway, name
                        self.add_ControlledPoint(GS(args[7], args[9], args[8], lat, lon, alt, args[4], args[5], args[6], args[10], " ".join(args[11:])))
                    elif lineCode in (NAVAIDS["OM"], NAVAIDS["MM"], NAVAIDS["IM"]):
                        # ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, name
                        self.add_ControlledPoint(MB(args[7], args[9], args[8], lat, lon, alt, args[4], args[5], args[6], args[10], " ".join(args[11:]), lineCode))
                    elif lineCode in (NAVAIDS["DME"], NAVAIDS["DMESA"]):
                        # 47.434333333 -122.306300000 369    11030 25 0.000 ISNQ  KSEA K1 SEATTLE-TACOMA INTL DME-ILS
                        # ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, name
                        self.add_ControlledPoint(DME(args[7], args[9], args[8], lat, lon, alt, args[4], args[5], args[6], " ".join(args[10:])))
                    elif lineCode == NAVAIDS["FPAP"]:
                        # 14  47.437969722 -122.311211111 429    61010 0.0 180.339 R16CY KSEA K1 16C LPV
                        # ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, runway, name
                        self.add_ControlledPoint(FPAP(args[7], args[9], args[8], lat, lon, alt, args[4], args[5], args[6], args[10], " ".join(args[11:])))
                    elif lineCode == NAVAIDS["GLS"]:
                        #
                        # ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, runway, name
                        self.add_ControlledPoint(GLS(args[7], args[9], args[8], lat, lon, alt, args[4], args[5], args[6], args[10], " ".join(args[11:])))
                    elif lineCode == NAVAIDS["LTPFTP"]:
                        # 16 47.463809028 -122.310985000 429    61010  56.6 300180.339 R16CY KSEA K1 16C WAAS
                        # ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, runway, name
                        self.add_ControlledPoint(LTPFTP(args[7], args[9], args[8], lat, lon, alt, args[4], args[5], args[6], args[10], " ".join(args[11:])))
                    else:
                        count -= 1
                        logging.warning("XPAirspace::loadNavaids: invalid navaid code %d.", lineCode)
                else:
                    if len(line) > 1:
                        logging.warning("XPAirspace::loadNavaids: invalid navaid data %s.", line)


            line = file.readline()
            line.strip()

        file.close()

        logging.debug("XPAirspace::loadNavaids: %d/%d navaids loaded.", len(self.vert_dict.keys()) - startLen, count)
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
                logging.info(line.strip())
            elif re.match("^99", line, flags=0):
                pass
            else:
                args = line.split()
                if len(args) == 11:  # names, start, end, direction, lowhigh, fl_floor, fl_ceil
                    src = self.find_ControlledPoint(args[1], args[0], args[2])
                    if src:
                        dst = self.find_ControlledPoint(args[4], args[3], args[5])
                        if dst:
                            if args[6] == DIRECTION["FORWARD"]:
                                self.add_edge(AirwaySegment(args[10], src, dst, True, args[7], args[8], args[9]))
                            elif args[6] == DIRECTION["BACKWARD"]:
                                self.add_edge(AirwaySegment(args[10], dst, src, True, args[7], args[8], args[9]))
                            else:
                                self.add_edge(AirwaySegment(args[10], src, dst, False, args[7], args[8], args[9]))
                            count += 1
                        else:
                            logging.debug("could not find end of segment %s, %s, %s, %s", args[10], args[4], args[3], args[5])
                    else:
                        logging.debug("could not find start of segment %s, %s, %s, %s", args[10], args[0], args[1], args[2])
                else:
                    if len(line) > 1:
                        logging.warning("XPAirspace::loadAirwaySegments: invalid segment data %s (%d).", line, count)

            line = file.readline()
            line.strip()

        file.close()

        logging.debug("XPAirspace::loadAirwaySegments: %d segments loaded.", len(self.edges_arr))
        return True


    def nearest_connected_vertex_not_airport(self, point: Feature):
        closest = None
        dist = float(math.inf)
        for p in self.vert_dict.values():
            if p.navtype != "APT" and len(p.adjacent) > 0:
                d = distance(point, p)
                if d < dist:
                    dist = d
                    closest = p
        return [closest, dist]

        # fc = list(map(lambda x: Feature(geometry=x.geometry, id=x.id), self.vert_dict.values()))
        # print(len(fc))
        # print(fc[0])
        # fc.reverse()
        # return nearest_point(point, FeatureCollection(features=fc))


    def mkBbox(self, a, b, enlarge: float=None):
        """
        Make a larger bounding box. We take direct line from A to B and extends the bounding box
        by large kilometers in direction of NE et and SW.

        :param      a:      { parameter_description }
        :type       a:      { type_description }
        :param      b:      { parameter_description }
        :type       b:      { type_description }
        :param      large:  The large
        :type       large:  { type_description }
        """
        bb = bbox(LineString([a.geometry.coordinates, b.geometry.coordinates]))
        if enlarge is not None:
            ll = Feature(geometry=Point((bb[0], bb[1])))
            ur = Feature(geometry=Point((bb[2], bb[3])))
            ll1 = destination(ll, enlarge, 225)  # going SW
            ur1 = destination(ur, enlarge, 45)   # going NE
            bb = bbox(LineString([ll1.geometry.coordinates, ur1.geometry.coordinates]))
        return bb


    def mkRoute(self, src, dst):
        """
        Finds the closest vertex to src, the closest vertex to dst and then
        find a route between those 2 vertices.

        :param      src:  The source
        :type       src:  { type_description }
        :param      dst:  The destination
        :type       dst:  { type_description }
        """

        # self.cleanup()

        asrc = self.find_ControlledPoint("WORLD", src, -1)
        if not asrc:
            return [False, "Could not find departure airport"]

        vsrc = self.nearest_connected_vertex_not_airport(asrc)
        if not vsrc[0]:
            return [False, "Could not find vertex close to departure"]
        logger.debug("XPXPAirspace::mkRoute: from %s", vsrc[0].id)

        adst = self.find_ControlledPoint("WORLD", dst, -1)
        if not adst:
            return [False, "Could not find arrival airport"]

        vdst = self.nearest_connected_vertex_not_airport(adst)
        if not vdst[0]:
            return [False, "Could not find vertex close to arrival"]
        logger.debug("XPXPAirspace::mkRoute: to %s", vdst[0].id)

        # We only keep vertices in a boundingbox around the flight
        self.bbox = self.mkBbox(asrc, adst, 150)

        bbp = bbox_polygon(self.bbox)
        logger.debug("Graph::mkRoute: bounding box %s", bbp)
        route = Route(self, vsrc[0].id, vdst[0].id, "", {"bbox": bbp})
        route.find()
        if route.found():  # second attempt may have worked
            return (True, route)

        return (False, "We could not find a route to your destination.")
# Algorithm:0
# Flight needs: AIRPORT, runway, procedure name (departure and arrival)
# Touch down zone
# Nice to have: Parking/ramp (departure and arrival)
# Find SID for departure. Start path with departure airport + SID.
# Find STAR for arrival. Terminate path with STAR and arrival airport.
# Find last of SID and first of STAR, find close vertices (ideally on LOW airways)
# Make transitions close to last SID to (low) airway
# Make transitions (low) airway to close to first STAR
#
#
