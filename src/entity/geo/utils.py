from geojson import Point, LineString, Feature
from turfpy.measurement import destination, bbox

import logging

logger = logging.getLogger("geoutils")

def mkBbox(a, b, enlarge: float = None):
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
    bb = None

    if enlarge is None:
        bb = bbox(LineString([a.geometry.coordinates, b.geometry.coordinates]))
    else:
        ll = Feature(geometry=Point((bb[0], bb[1])))
        ur = Feature(geometry=Point((bb[2], bb[3])))
        ll1 = destination(ll, enlarge, 225)  # going SW
        ur1 = destination(ur, enlarge, 45)   # going NE
        bb = bbox(LineString([ll1.geometry.coordinates, ur1.geometry.coordinates]))

    return bb