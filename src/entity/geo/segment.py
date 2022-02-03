"""
Handy wrapper class for line (2-point linestring with named extremities)
"""
from geojson import Point, LineString, Polygon
from turfpy.measurement import destination, distance, bearing

import logging
logger = logging.getLogger("GeoJSON")



class Segment(LineString):
    """
    Utility class for 2 point LineString.
    """

def __init__(self, start: Point, end: Point, width: float = None):
    LineString.__init__(self, ((start.coordinates, end.coordinates)))
    self.start = start
    self.end = end
    self.width = width


    def length(self):
        """
        Returns length of line.
        """
        return distance(self.start, self.end)


    def bearing(self):
        """
        Returns bearing of line in decimal degrees (0-359).
        """
        return bearing(self.start, self.end)


    def surface(self, width: float=None, closed: bool=True):
        """
        Returns a polygon with no buffer on extremities, and width/2 buffer along the line.
        Represent a surface segment of the underlying feature (runways, taxiways, parking...)

        :param      width:  The width
        :type       width:  { type_description }

        :returns:   { description_of_the_return_value }
        :rtype:     { return_type_description }
        """
        w = width
        if w is None:
            if self.width is None:
                logger.warning(":surface: no width")
                return None
            w = self.width

        brng = self.bearing()
        # one side of centerline
        brng = brng + 90
        a0 = destination(self.start, w / 2, brng)
        a2 = destination(self.end, w / 2, brng)
        # other side of centerline
        brng = brng - 90
        a1 = destination(self.start, w / 2, brng)
        a3 = destination(self.end, w / 2, brng)
        # join
        if closed:
            return Feature(geometry=Polygon([a0, a1, a3, a2, a0]))

        return Feature(geometry=Polygon([a0, a1, a3, a2]))
