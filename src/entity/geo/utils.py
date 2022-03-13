import random
import logging

from geojson import Point, LineString, Polygon, Feature, FeatureCollection
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
    # move on dist (meters) on linestring from currpos (which is between idx and idx+1)
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
        # logger.debug(":moveOn: completed segment %d, move on segment %d, %f left to run" % (idx, idx + 1, dist - left))
        return moveOn(arr, idx + 1, nextp, dist - left)
    # we progress towards next point without reaching it
    brng = bearing(arr[idx], nextp)
    dest = destination(currpos, dist, brng, {"units": "m"})  # dist in m
    # logger.debug(":moveOn: distance to run reached, %f left on segment %d" % (left - dist, idx + 1))
    return (dest, idx)


def line_intersect(line1, line2):
    coords1 = line1["geometry"]["coordinates"]
    coords2 = line2["geometry"]["coordinates"]
    x1 = coords1[0][0]
    y1 = coords1[0][1]
    x2 = coords1[1][0]
    y2 = coords1[1][1]
    x3 = coords2[0][0]
    y3 = coords2[0][1]
    x4 = coords2[1][0]
    y4 = coords2[1][1]
    denom = (y4 - y3) * (x2 - x1) - (x4 - x3) * (y2 - y1)
    numeA = (x4 - x3) * (y1 - y3) - (y4 - y3) * (x1 - x3)
    numeB = (x2 - x1) * (y1 - y3) - (y2 - y1) * (x1 - x3)
    if denom == 0:
        if numeA == 0 and numeB == 0:
            return None
        return None
    uA = numeA / denom
    uB = numeB / denom
    if uA >= 0 and uA <= 1 and uB >= 0 and uB <= 1:
        x = x1 + uA * (x2 - x1)
        y = y1 + uA * (y2 - y1)
        return Feature(geometry=Point([x, y]))
    return None


def asLineString(features):
    # reduce(lambda num1, num2: num1 * num2, my_numbers, 0)
    coords = []
    for x in features:
        coords.append(x["geometry"]["coordinates"])
    # coords = reduce(lambda x, coords: coords + x["geometry"]["coordinates"], self.moves, [])
    return LineString(coords)


def cleanFeature(f):
    return Feature(geometry=f["geometry"], properties=f["properties"])


def cleanFeatures(fa):
    c = []
    for f in fa:
        c.append(cleanFeature(f))
    return c


def getFeatureCollection(features, addline: bool = False):
    fc = features
    if addline:
        ls = Feature(geometry=asLineString(features))
        fc = fc + [ls]
    return FeatureCollection(features=cleanFeatures(fc))


def printFeatures(features, info, addline: bool = False):
    dashlen = 50
    print(f">>> {info} " + ("-" * dashlen))
    print(getFeatureCollection(features, addline))
    print("-" * (dashlen + 5 + len(info)))


def findFeatures(arr, criteria):
    res = []
    for f in arr:
        ok = True
        for k in criteria:
            ok = (ok and k in f["properties"] and f["properties"][k] == criteria[k])
        if ok:
            res.append(f)
    return res


def findFeaturesCWL(arr, criteria):
    res = []
    for f in arr:
        ok = True
        for k in criteria:
            ok = (ok and k in f["properties"] and (criteria[k] in f["properties"][k].split("|") or f["properties"][k] == "*"))
        if ok:
            res.append(f)
    return res
