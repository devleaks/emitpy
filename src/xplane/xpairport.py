# Airport Utility Class
# Airport information container: name, taxi routes, runways, ramps, etc.
#
import os.path
import re
import math
import logging

SYSTEM_DIRECTORY = ".."

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
        self.graph = Graph()
        self.runways = {}
        self.ramps = {}
        self.cifp = {}


    def load(self):
        SCENERY_PACKS = os.path.join(SYSTEM_DIRECTORY, "Custom Scenery", "scenery_packs.ini")
        scenery_packs = open(SCENERY_PACKS, "r")
        scenery = scenery_packs.readline()
        scenery = scenery.strip()

        while not self.loaded and scenery:  # while we have not found our airport and there are more scenery packs
            if re.match("^SCENERY_PACK", scenery, flags=0):
                # logging.debug("SCENERY_PACK %s", scenery.rstrip())
                scenery_pack_dir = scenery[13:-1]
                scenery_pack_apt = os.path.join(scenery_pack_dir, "Earth nav data", "apt.dat")
                # logging.debug("APT.DAT %s", scenery_pack_apt)

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
                                logging.info("Airport::load: Found airport %s '%s' in '%s'.", newparam[4], self.name, scenery_pack_apt)
                                self.scenery_pack = scenery_pack_apt  # remember where we found it
                                self.lines.append(AptLine(line))  # keep first line
                                line = apt_dat.readline()  # next line in apt.dat
                                while line and not re.match("^1 ", line, flags=0):  # while we do not encounter a line defining a new airport...
                                    testline = AptLine(line)
                                    if testline.linecode() is not None:
                                        self.lines.append(testline)
                                    else:
                                        logging.debug("Airport::load: did not load empty line '%s'" % line)
                                    line = apt_dat.readline()  # next line in apt.dat
                                # Info 4.b
                                logging.info("Airport::load: Read %d lines for %s." % (len(self.lines), self.name))
                                self.loaded = True

                        if(line):  # otherwize we reached the end of file
                            line = apt_dat.readline()  # next line in apt.dat

                    apt_dat.close()

            scenery = scenery_packs.readline()

        scenery_packs.close()
        return self.loaded


    def dump(self, filename):
        aptfile = open(filename, "w")
        for line in self.lines:
            aptfile.write("%d %s\n" % (line.linecode(), line.content()))
        aptfile.close()


    def ldRunways(self):
        #     0     1 2 3    4 5 6 7    8            9               10 11  1213141516   17           18              19 20  21222324
        # 100 60.00 1 1 0.25 1 3 0 16L  25.29609337  051.60889908    0  300 2 2 1 0 34R  25.25546269  051.62677745    0  306 3 2 1 0
        runways = {}

        for aptline in self.lines:
            if aptline.linecode() == 100:  # runway
                args = aptline.content().split()
                runway = Polygon.mkPolygon(args[8], args[9], args[17], args[18], float(args[0]))
                runways[args[7]] = Runway(args[7], args[0], args[8], args[9], args[17], args[18], runway)
                runways[args[16]] = Runway(args[16], args[0], args[17], args[18], args[8], args[9], runway)

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
                if args[3] != "misc":
                    rampName = " ".join(args[5:])
                    ramp = Ramp(rampName, args[2], args[0], args[1])
                    ramp.locationType = args[3]
                    ramp.aircrafts = args[4].split("|")
                    ramps[rampName] = ramp
            elif ramp and aptline.linecode() == 1301: # ramp details
                args = aptline.content().split()
                ramp.icaoType = args[0]
                ramp.operationType = args[1]
                if len(args) > 2 and args[2] != "":
                    ramp.airlines = args[2].split(",")
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
            line = line.strip()
            la = line.split(":")
            lc = la[1].split(",")
            if not la[0] in self.cifp:
                self.cifp[la[0]] = {}

            if la[0] == SID:
                self.cifp[SID][lc[2]] = lc
                logging.debug("found %s %s", la[0], lc[2])
            elif la[0] == STAR:
                self.cifp[STAR][lc[2]] = lc
                logging.debug("found %s %s", la[0], lc[2])
            elif la[0] == APPROACH:
                self.cifp[APPROACH][lc[2]] = lc
                logging.debug("found %s %s", la[0], lc[2])
            elif la[0] == PROCDATA:
                self.cifp[PROCDATA][lc[2]] = lc
                logging.debug("found %s %s", la[0], lc[2])
            elif la[0] == RUNWAY:
                if not lc[0] in self.cifp[la[0]]:
                    self.cifp[la[0]][lc[0]] = lc
                    logging.debug("found %s %s", la[0], lc[0])
            else:
                logging.warning("invalid start of line in CIFP", line)

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
