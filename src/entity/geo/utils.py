import random
import logging

from geojson import Point, LineString, Polygon, Feature
from turfpy.measurement import destination, bearing, bbox

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
        bb = bbox(LineString([a["geometry"]["coordinates"], b["geometry"]["coordinates"]]))
    else:
        ll = Feature(geometry=Point((bb[0], bb[1])))
        ur = Feature(geometry=Point((bb[2], bb[3])))
        ll1 = destination(ll, enlarge, 225)  # going SW
        ur1 = destination(ur, enlarge, 45)   # going NE
        bb = bbox(LineString([ll1["geometry"]["coordinates"], ur1["geometry"]["coordinates"]]))

    return bb


def mkPolygon(lat1, lon1, lat2, lon2, width):
    p1 = Feature(geometry=Point((lon1, lat1)))
    p2 = Feature(geometry=Point((lon2, lat2)))
    brng = bearing(p1, p2)
    # one side of centerline
    brng = brng + 90
    a0 = destination(p1, brng, width / 2)
    a2 = destination(p2, brng, width / 2)
    # other side of centerline
    brng = brng - 90
    a1 = destination(p1, brng, width / 2)
    a3 = destination(p2, brng, width / 2)
    # join
    return Polygon(list(map(lambda x: x["geometry"]["coordinates"], [a0, a1, a3, a2])))


def jitter(point: Point, r: float = 0):
    if r == 0:
        return point["geometry"]["coordinates"]
    j = destination(Feature(geometry=point), random.random() * abs(r) / 1000, random.random() * 360)
    # should add some vertical uncertainty as well...
    if len(j["geometry"]["coordinates"]) == 3:  # alt = alt ± jitter
        j["geometry"]["coordinates"][2] = j["geometry"]["coordinates"][2] + ((random.random() * abs(r) / 1000) * (-1 if random.random() > 0.5 else 1))
    return j["geometry"]["coordinates"]
