# Geographic utility functions
import random
import logging
import json
import math
from typing import List

from emitpy.geo.turf import Point, LineString, Polygon, Feature, FeatureCollection
from emitpy.geo.turf import distance, destination, bearing
from emitpy.geo import FeatureWithProps

logger = logging.getLogger("geoutils")


def mkPolygon(lat1, lon1, lat2, lon2, width, as_feature: bool = False):
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
    ret = Polygon([list(list(map(lambda x: x.geometry.coordinates, [a0, a1, a3, a2, a0])))])
    if as_feature:
        ret = Feature(geometry=ret)
    return ret


def mkCircle(lat1, lon1, radius, steps: int = 9, as_feature: bool = False):
    center = Feature(geometry=Point((lon1, lat1)))
    step = 360 / steps
    angle = 0.0
    polygon = []
    for i in range(steps):
        pt = destination(center, radius, angle)  # destination returns a Feature
        polygon.append(pt.geometry.coordinates)
        angle = angle + step
    polygon.append(polygon[0])  # closing
    ret = Polygon(polygon)
    if as_feature:
        ret = Feature(geometry=ret)
    return ret


def jitter(point: Point, r: float = 0):
    if r == 0:
        return point.geometry.coordinates
    j = destination(Feature(geometry=point), random.random() * abs(r) / 1000, random.random() * 360)
    # should add some vertical uncertainty as well...
    if len(j.geometry.coordinates) == 3:  # alt = alt ± jitter
        j.geometry.coordinates[2] = j.geometry.coordinates[2] + ((random.random() * abs(r) / 1000) * (-1 if random.random() > 0.5 else 1))
    return j.geometry.coordinates


def moveOn(arr, idx, currpos, dist):
    # move on dist (meters) on linestring from currpos (which is between idx and idx+1)
    # are we at the end of the line string?
    if idx == len(arr) - 1:
        logger.debug("arrived")
        return (arr[-1], len(arr) - 1)
    if idx == len(arr) - 2:
        logger.debug(f"last segment {idx}, {dist} left")
        # do we reach destination?
        left = distance(currpos, arr[-1], "m")
        if left < dist:  # we reached destination
            logger.debug("destination reached")
            return (arr[-1], len(arr) - 1)
        # we do not reach destination, so we move towards it
        # we can continue with regular algorithm
    nextp = arr[idx + 1]
    left = distance(currpos, nextp, "m")  # distance returns km
    if left < dist:  # we reach the next point at least. Move to it, then continue.
        # logger.debug("completed segment %d, move on segment %d, %f left to run" % (idx, idx + 1, dist - left))
        return moveOn(arr, idx + 1, nextp, dist - left)
    # we progress towards next point without reaching it
    brng = bearing(arr[idx], nextp)
    dest = destination(currpos, dist, brng, units="m")  # dist in m
    # logger.debug("distance to run reached, %f left on segment %d" % (left - dist, idx + 1))
    return (dest, idx)


def line_intersect(line1, line2):
    coords1 = line1.geometry.coordinates
    coords2 = line2.geometry.coordinates
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
    return LineString([f.geometry.coordinates for f in features])


def asFeatureLineStringWithTimestamps(features: List[FeatureWithProps]):
    ls = []
    rt = []
    at = []

    for f in features:
        if f.geometry["type"] == "Point":
            ls.append(f.geometry.coordinates)
            rt.append(f.getRelativeEmissionTime())
            at.append(f.getAbsoluteEmissionTime())

    props = features[0].properties
    props["time"] = at
    props["reltime"] = rt

    return json.dumps(FeatureCollection(features=[Feature(geometry=LineString(ls), properties=props)]), indent=4)


def shortest_ls(lss):
    shortest = None
    dist = math.inf
    for ls in lss:
        d = lsLength(ls)
        if d < dist:
            shortest = ls
            dist = d
    return (shortest, dist)


def cleanFeature(f):
    """Return a pure simple GeoJSON Feature (some libraries do not work if not fed with pure GeoJSON Feature)

    Args:
        f ([type]): Feature to convert

    Returns:
        [type]: simpler Feature with just geomerty and propreties
    """
    return Feature(geometry=f.geometry, properties=f.properties)


def cleanFeatures(fa):
    """Return a list of pure simple GeoJSON Features

    Args:
        fa ([type]): Features to convert

    Returns:
        [Feature]: Converted features
    """
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
    print(f"*** {info} " + ("-" * dashlen))
    print(getFeatureCollection(features, addline))
    print("-" * (dashlen + 5 + len(info)))


def findFeatures(arr, criteria):
    res = []
    for f in arr:
        ok = True
        for k, v in criteria.items():  # AND all criteria
            ok = ok and (f.properties.get(k) == v)
        if ok:
            res.append(f)
    return res


def findFeaturesCWL(arr, criteria):
    res = []
    for f in arr:
        ok = True
        for k in criteria:
            ok = ok and k in f.properties and (criteria[k] in f.properties[k].split("|") or f.properties[k] == "*")
        if ok:
            res.append(f)
    return res


def ls_length(ls: LineString):
    dist = 0
    last = None
    for coord in ls.geometry.coordinates:
        if last is not None:
            dist = dist + distance(Feature(Point(last)), Feature(Point(coord)))
        last = coord
    return dist


def ls_point_at(ls: LineString, dist: float):
    # Returns point at distance dist since begining of linestring
    def ffp(p):
        return Feature(geometry=Point(p))

    total = 0
    start = ls.coordinates[0]
    i = 1
    while total < dist and i < len(ls.coordinates):
        d = distance(Point(start), Point(ls.coordinates[i]), units="m")
        prevtotal = total
        total = total + d
        start = ls.coordinates[i]
        i = i + 1

    if total < dist:  # requested distance is longer than linestring
        return None

    lastvertex = ls.coordinates[i - 2]
    left = dist - prevtotal
    brng = bearing(ffp(lastvertex), ffp(ls.coordinates[i - 1]))
    dest = destination(ffp(lastvertex), left, brng, units="m")
    return dest


def get_bounding_box(points, rounding: float | None = None):
    """
    get bounding box of point set.
    assumes  90 (north) <= lat <= -90 (south), and -180 (west) < lon < 180 (east)
    """
    north = -90
    south = 90
    east = -180
    west = 180
    for f in points:
        lat = f.lat()
        if lat > north:
            north = lat
        if lat < south:
            south = lat
        lon = f.lon()
        if lon < west:
            west = lon
        if lon > east:
            east = lon
    if rounding is not None:  # will later allow for finer rounding, but round to degrees for grib file resolution matching
        north = math.ceil(north)
        south = math.floor(south)
        west = math.floor(west)
        east = math.ceil(east)
    return (north, east, south, west)


def mk180(a):
    if a > 180:
        return mk180(a - 360)
    if a < -180:
        return mk180(a + 360)
    return a


def mk360(a):
    # Make angle in [0, 360]
    if a < 0:
        return mk360(a + 360)
    elif a >= 360:
        return mk360(a - 360)
    return a


def add_speed(r1, r2):
    # https://math.stackexchange.com/questions/1365622/adding-two-polar-vectors
    p21 = math.radians(r2[1]) - math.radians(r1[1])
    r = math.sqrt(r1[0] * r1[0] + r2[0] * r2[0] + 2 * r1[0] * r2[0] * math.cos(p21))
    phi = math.radians(r1[1]) + math.atan2(r2[0] * math.sin(p21), r1[0] + r2[0] * math.cos(p21))
    return (r, math.degrees(phi))


def subtract_speed(r1, r2):
    # Add -r2, r2 going in opposite direction, direction supplied in degrees.
    opp = r2[1] + 180
    if opp > 360:
        opp = opp - 360
    return add_speed(r1, (r2[0], opp))


def adjust_speed_vector(tas, ws):
    # Add gs and ws vector, and adjust gs angle (heading) so that final course remain original gs course.
    # All vectors supplied and returned as (speed[m/s], angle[DEG 0-360°])
    # ws never changes, for gs, only heading is adjusted.
    # resulting new gs heads towards original gs (course), speed adjusted accordingly
    MAX_ITERATIONS = 4
    ACCEPTABLE = 0.01

    # print(f"in ==> tas={tas[0]}, req. heading={tas[1]}, ws={ws}")

    goal = tas[1]
    newtas = tas  # initial value
    gs = add_speed(newtas, ws)  # first iteration
    delta = gs[1] - goal
    # print(f"iter0 {newtas}, ws={ws}, gs={gs}, diff angle={delta}")
    i = 0
    while i < MAX_ITERATIONS and abs(delta) > ACCEPTABLE:
        delta = gs[1] - goal
        newangle = newtas[1] - delta
        newtas = (tas[0], newangle)
        gs = add_speed(newtas, ws)
        # print(f"iter1 {newtas}, ws={ws}, gs={gs}, diff angle={delta}")
        i = i + 1
    # print(f"out==> gs={round(gs[0],1)} course={round(gs[1], 1)} (diff={round(tas[1]-gs[1], 2)}), heading={round(newtas[1], 1)} (diff={round(tas[1]-newtas[1], 2)})")
    return (newtas, gs)
