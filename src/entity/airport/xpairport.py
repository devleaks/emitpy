# Airport Utility Class
# Airport information container: name, taxi routes, runways, ramps, etc.
#
import os.path
import re
import math
import logging

from geojson import Point, Feature
from turfpy.measurement import distance

from entity.parameters import DATA_DIR
from entity.utils.graph import Vertex, Edge, Graph
from entity.utils.geoline import Line


SYSTEM_DIRECTORY = os.path.join(DATA_DIR, "x-plane")

class AptLine:
    # APT.DAT line for this airport
    def __init__(self, line):
        self.arr = line.split()
        if len(self.arr) == 0:
            logging.debug("AptLine::linecode: empty line? '%s'", line)

    def linecode(self):
        if len(self.arr) > 0:
            return int(self.arr[0])
        return None

    def content(self):
        if len(self.arr) > 1:
            return " ".join(self.arr[1:])
        return None  # line has no content


SID = "SID"
STAR = "STAR"
APPROACH = "APPCH"
RUNWAY = "RWY"
PROCDATA = "PRDAT"

class CIFPLine:
    # CIFP line for this airport
    def __init__(self, line):
        self.procedure = None
        self.params = []
        a = line.split(":")
        if len(a) == 0:
            logging.debug("CIFPLine::CIFPLine: invalid line '%s'", line)
        self.procedure = a[0]
        self.params = a[1].split(",")
        if len(self.params) == 0:
            logging.debug("CIFPLine::CIFPLine: invalid line '%s'", line)

    def proc(self):
        return self.procedure

    def name(self):
        if self.proc() == RUNWAY:
            return self.params[0]
        return self.params[2]

    def seq(self):
        return int(self.params[0])

    def rwy(self):
        return int(self.params[3])

    def content(self):
        return self.params.join(",")



class XPAirport:
    """Airport represetation (limited to FTG needs)"""
    # Should be split with generic non dependant airport and airport with routing, dependant on Graph

    def __init__(self, icao):
        self.icao = icao
        self.name = ""
        self.atc_ground = None
        self.altitude = 0  # ASL, in meters
        self.loaded = False
        self.scenery_pack = False
        self.lines = []
        self.runways = {}
        self.ramps = {}
        self.cifp = {}
        self.taxiways = Graph()


    def load(self):
        SCENERY_PACKS = os.path.join(SYSTEM_DIRECTORY, "Custom Scenery", "scenery_packs.ini")
        scenery_packs = open(SCENERY_PACKS, "r")
        scenery = scenery_packs.readline()
        scenery = scenery.strip()

        while not self.loaded and scenery:  # while we have not found our airport and there are more scenery packs
            if re.match("^SCENERY_PACK", scenery, flags=0):
                logging.debug("SCENERY_PACK %s", scenery.rstrip())
                scenery_pack_dir = scenery[13:-1]
                scenery_pack_apt = os.path.join(SYSTEM_DIRECTORY, scenery_pack_dir, "Earth nav data", "apt.dat")
                logging.debug("APT.DAT %s", scenery_pack_apt)

                if os.path.isfile(scenery_pack_apt):
                    apt_dat = open(scenery_pack_apt, "r", encoding='utf-8')
                    line = apt_dat.readline()

                    while not self.loaded and line:  # while we have not found our airport and there are more lines in this pack
                        if re.match("^1 ", line, flags=0):  # if it is a "startOfAirport" line
                            newparam = line.split()  # if no characters supplied to split(), multiple space characters as one
                            # logging.debug("airport: %s" % newparam[4])
                            if newparam[4] == self.icao:  # it is the airport we are looking for
                                self.name = " ".join(newparam[5:])
                                self.altitude = newparam[1]
                                # Info 4.a
                                logging.info("XPAirport::load: Found airport %s '%s' in '%s'.", newparam[4], self.name, scenery_pack_apt)
                                self.scenery_pack = scenery_pack_apt  # remember where we found it
                                self.lines.append(AptLine(line))  # keep first line
                                line = apt_dat.readline()  # next line in apt.dat
                                while line and not re.match("^1 ", line, flags=0):  # while we do not encounter a line defining a new airport...
                                    testline = AptLine(line)
                                    if testline.linecode() is not None:
                                        self.lines.append(testline)
                                    else:
                                        logging.debug("XPAirport::load: did not load empty line '%s'" % line)
                                    line = apt_dat.readline()  # next line in apt.dat
                                # Info 4.b
                                logging.info("XPAirport::load: Read %d lines for %s." % (len(self.lines), self.name))
                                self.loaded = True

                        if(line):  # otherwize we reached the end of file
                            line = apt_dat.readline()  # next line in apt.dat

                    apt_dat.close()

            scenery = scenery_packs.readline()

        scenery_packs.close()
        return self.loaded


    def ldRunways(self):
        #     0     1 2 3    4 5 6 7    8            9               10 11  1213141516   17           18              19 20  21222324
        # 100 60.00 1 1 0.25 1 3 0 16L  25.29609337  051.60889908    0  300 2 2 1 0 34R  25.25546269  051.62677745    0  306 3 2 1 0
        runways = {}

        for aptline in self.lines:
            if aptline.linecode() == 100:  # runway
                args = aptline.content().split()
                # runway = Polygon.mkPolygon(args[8], args[9], args[17], args[18], float(args[0]))
                # runways[args[7]] = Runway(args[7], args[0], args[8], args[9], args[17], args[18], runway)
                # runways[args[16]] = Runway(args[16], args[0], args[17], args[18], args[8], args[9], runway)

        self.runways = runways
        logging.debug("ldRunways: added %d runways", len(runways.keys()))
        return runways


    def ldRamps(self):
        # 1300  25.26123160  051.61147754 155.90 gate heavy|jets|turboprops A1
        # 1301 E airline
        # 1202 ignored.
        ramps = {}

        ramp = False
        for aptline in self.lines:
            if aptline.linecode() == 1300: # ramp
                args = aptline.content().split()
                # if args[3] != "misc":
                #     rampName = " ".join(args[5:])
                #     ramp = Ramp(rampName, args[2], args[0], args[1])
                #     ramp.locationType = args[3]
                #     ramp.aircrafts = args[4].split("|")
                #     ramps[rampName] = ramp
            elif ramp and aptline.linecode() == 1301: # ramp details
                args = aptline.content().split()
                # ramp.icaoType = args[0]
                # ramp.operationType = args[1]
                # if len(args) > 2 and args[2] != "":
                #     ramp.airlines = args[2].split(",")
            else:
                ramp = False

        self.ramps = ramps
        logging.debug("ldRamps: added %d ramps", len(ramps.keys()))
        return ramps


    def ldCIFP(self):
        """
        Loads Coded Instrument Flight Procedures

        :returns:   { description_of_the_return_value }
        :rtype:     { return_type_description }
        """
        CIFP = os.path.join(SYSTEM_DIRECTORY, "Resources", "default data", "CIFP", self.icao + ".dat")
        cifp_file = open(CIFP, "r")
        line = cifp_file.readline()

        while line:
            cifpline = CIFPLine(line.strip())
            procty = cifpline.proc()
            procname = cifpline.name()

            if not procty in self.cifp:
                self.cifp[procty] = {}

            if not procname in self.cifp[procty]:
                self.cifp[procty][procname] = []

            self.cifp[procty][procname].append(cifpline)

            # if arr[0] == "SID":
            #     idx[0] = i-1
            # elif line[:5] == "STAR":
            #     idx[1] = i-1
            # elif line[:6] == "APPCH":
            #     idx[2] = i-1
            # elif line[:4] == "RWY":
            #     idx[3] = i-1
            # else:
            #     logging.warning("invalid start of line in CIFP", line)

            line = cifp_file.readline()

        logging.debug("XPAirport::ldCIFP: SID: %s", self.cifp["SID"].keys())
        logging.debug("XPAirport::ldCIFP: STAR: %s", self.cifp["STAR"].keys())
        logging.debug("XPAirport::ldCIFP: Approaches: %s", self.cifp["APPCH"].keys())
        logging.debug("XPAirport::ldCIFP: Runways: %s", self.cifp["RWY"].keys())


    # Collect 1201 and (102,1204) line codes and create routing network (graph) of taxiways
    def ldTaxiwayNetwork(self):
        # 1201  25.29549372  051.60759816 both 16 unnamed entity(split)
        def addVertex(aptline):
            args = aptline.content().split()
            return self.taxiways.add_vertex(Vertex(node=args[3], point=Point((float(args[0]), float(args[1]))), usage=[ args[2]], name=" ".join(args[3:])))

        vertexlines = list(filter(lambda x: x.linecode() == 1201, self.lines))
        v = list(map(addVertex, vertexlines))
        logging.debug("mkRoutingNetwork: added %d vertices" % len(v))

        # 1202 20 21 twoway runway 16L/34R
        # 1204 departure 16L,34R
        # 1204 arrival 16L,34R
        # 1204 ils 16L,34R
        edgeCount = 0   # just for info
        edgeActiveCount = 0
        edge = False
        for aptline in self.lines:
            if aptline.linecode() == 1202: # edge
                args = aptline.content().split()
                if len(args) >= 4:
                    src = self.taxiways.get_vertex(args[0])
                    dst = self.taxiways.get_vertex(args[1])
                    print(src.geometry, dst.geometry)
                    cost = distance(src.geometry, dst.geometry)
                    edge = None
                    if len(args) == 5:
                        # args[2] = {oneway|twoway}, args[3] = {runway|taxiway}
                        edge = Edge(src=src, dst=dst, weight=cost, directed=(args[2]=="oneway"), usage=[args[3]], name=args[4])
                    else:
                        edge = Edge(src, dst, cost, args[2], args[3], "")
                    self.taxiways.add_edge(edge)
                    edgeCount += 1
                else:
                    logging.debug("Airport::mkRoutingNetwork: not enough params %d %s.", aptline.linecode(), aptline.content())
            elif aptline.linecode() == 1204 and edge:
                args = aptline.content().split()
                if len(args) >= 2:
                    edge.use(args[0], True)
                    edge.use(args[1], True)
                    edgeActiveCount += 1
                else:
                    logging.debug("Airport::mkRoutingNetwork: not enough params %d %s.", aptline.linecode(), aptline.content())
            else:
                edge = False

        # Info 6
        logging.info("Airport::mkRoutingNetwork: added %d nodes, %d edges (%d enhanced).", len(vertexlines), edgeCount, edgeActiveCount)
        return True



