import random
import logging

from geojson import Point, LineString, Polygon, Feature
from turfpy.measurement import distance, destination, bearing, bbox

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
    a0 = destination(p1, width / 2, brng)
    a2 = destination(p2, width / 2, brng)
    # other side of centerline
    brng = brng - 90
    a1 = destination(p1, width / 2, brng)
    a3 = destination(p2, width / 2, brng)
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


def moveOn(arr, idx, currpos, dist):
    # are we at the end of the line string?
    if idx == len(arr) - 1:
        logger.debug(":moveOn: arrived")
        return (arr[-1], len(arr) - 1)
    if idx == len(arr) - 2:
        logger.debug(":moveOn: last segment %d, %f left" % (idx, dist))
        # do we reach destination?
        left = distance(currpos, arr[-1], 'm')
        if left < dist:  # we reached destination
            logger.debug(":moveOn: destination reached")
            return (arr[-1], len(arr) - 1)
        # we do not reach destination, so we move towards it
        # we can continue with regular algorithm
    nextp = arr[idx + 1]
    left = distance(currpos, nextp, 'm') # distance returns km
    if left < dist:  # we reach the next point at least. Move to it, then continue.
        logger.debug(":moveOn: completed segment %d, move on segment %d, %f left to run" % (idx, idx + 1, dist - left))
        return moveOn(arr, idx + 1, nextp, dist - left)
    # we progress towards next point without reaching it
    brng = bearing(arr[idx], nextp)
    dest = destination(currpos, dist, brng, {"units": "m"})  # dist in m
    logger.debug(":moveOn: distance to run reached, %f left on segment %d" % (left - dist, idx + 1))
    return (dest, idx)
