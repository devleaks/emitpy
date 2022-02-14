"""
Handy wrapper class for line (2-point linestring with named extremities)
"""
from geojson import Point, LineString, Polygon
from turfpy.measurement import destination, distance, bearing
from ..geo import Segment

import logging
logger = logging.getLogger("Runway")


class Runway(Segment):
    """
    Utility class for 2 point LineString.
    """

def __init__(self, name: str, start: Point, end: Point, width: float = None):
    Segment.__init__(self, start=start, end=end, width=width)
    self.name = name  # RWxx[L|R|C]

    self.rnum = int(name[3, 5])
    self.rpos = name[-1] if name[-1] in ("L", "C", "R") else None

    logger.debug("Runway::__init__: %s %s" % (name, self.opposite()))


    def opposite(self):
        n = self.rnum + 18
        if n > 36:
            n = n - 36
        p = self.rpos
        if self.rpos is not None:
            if self.rpos == "L":
                p = "R"
            elif self.rpos == "R":
                p : "L"
        return ("RW%02d" % n) + (p if p is not None else "")