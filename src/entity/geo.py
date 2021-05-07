# Geographic geometry utility functions
# I tested geo-py but precision was inferior(?).
# I'd love to user pyturf but it does not have all function I need
# and it loads heavy packages.
# So I made the functions I need.
#
import math
from .geojson import Point

# Geology constants
R = 6371000            # Radius of third rock from the sun, in metres
FT = 12 * 0.0254       # 1 FOOT = 12 INCHES
NAUTICAL_MILE = 1.852  # Nautical mile in meters 6076.118ft=1nm


def toNm(m):
    return round((m/1000) / NAUTICAL_MILE)


def toFeet(m):
    return round(m / FT)


def toMeter(ft):
    return round(ft * FT)


def toKn(kmh):
    return kmh / NAUTICAL_MILE


def toKmh(kn):
    return kn * NAUTICAL_MILE


def convertAngleTo360(alfa):
    beta = alfa % 360
    if beta < 0:
        beta = beta + 360
    return beta


def turn(bi, bo):
    t = bi - bo
    if t < 0:
        t += 360
    if t > 180:
        t -= 360
    return t


def sign(x):  # there is no sign function in python...
    if x < 0:
        return -1
    elif x > 0:
        return 1
    return 0


def haversine(lat1, lat2, long1, long2): # in radians.
    dlat, dlong = lat2 - lat1, long2 - long1
    return math.pow(math.sin(dlat / 2), 2) + math.cos(lat1) * math.cos(lat2) * math.pow(math.sin(dlong / 2), 2)


def distance(p1, p2):  # in degrees.
    lat1, lat2 = math.radians(p1.lat), math.radians(p2.lat)
    long1, long2 = math.radians(p1.lon), math.radians(p2.lon)
    a = haversine(lat1, lat2, long1, long2)
    return 2 * R * math.asin(math.sqrt(a))  # in m


def bearing(src, dst):
    lat1 = math.radians(src.lat)
    lon1 = math.radians(src.lon)
    lat2 = math.radians(dst.lat)
    lon2 = math.radians(dst.lon)

    y = math.sin(lon2 - lon1) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(lon2 - lon1)
    t = math.atan2(y, x)
    brng = convertAngleTo360(math.degrees(t))  # in degrees
    return brng


def destination(src, brngDeg, d):
    lat = math.radians(src.lat)
    lon = math.radians(src.lon)
    brng = math.radians(brngDeg)
    r = d / R

    lat2 = math.asin(math.sin(lat) * math.cos(r) + math.cos(lat) * math.sin(r) * math.cos(brng))
    lon2 = lon + math.atan2(math.sin(brng) * math.sin(r) * math.cos(lat), math.cos(r) - math.sin(lat) * math.sin(lat2))
    return Point(math.degrees(lat2), math.degrees(lon2))


def lineintersect(line1, line2):
    # Finds intersection of line1 and line2. Returns Point() of intersection or None.
    # !! Source code copied from GeoJSON code where coordinates are (longitude, latitude).
    x1 = line1.start.lon
    y1 = line1.start.lat
    x2 = line1.end.lon
    y2 = line1.end.lat
    x3 = line2.start.lon
    y3 = line2.start.lat
    x4 = line2.end.lon
    y4 = line2.end.lat
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
        # return [x, y]  # x is longitude, y is latitude.
        return Point(y, x)
    return None


def nearestPointToLines(p, lines):
    # First the nearest point to a collection of lines.
    # Lines is an array if Line()
    # Returns the point and and distance to it.
    nearest = None
    dist = math.inf
    for line in lines:
        d1 = distance(p, line.start)
        d2 = distance(p, line.end)
        dl = max(d1, d2)
        brng = bearing(line.start, line.end)
        brng += 90  # perpendicular
        p1 = destination(p, brng, dl)
        brng -= 180  # perpendicular
        p2 = destination(p, brng, dl)
        perpendicular = Line(p1, p2)
        intersect = lineintersect(perpendicular, line)
        if intersect:
            d = distance(p, intersect)
            if d < dist:
                dist = d
                nearest = intersect

    return [nearest, distance]


def pointInPolygon(point, polygon):
    # this will do. We do very local geometry (500m around current location)
    # pt is [x,y], pol is [[x,y],...].
    pt = point.coords()
    pol = polygon.coords()
    inside = False
    for i in range(len(pol)):
        x0, y0 = pol[i]
        x1, y1 = pol[(i + 1) % len(pol)]
        if not min(y0, y1) < pt[1] <= max(y0, y1):
            continue
        if pt[0] < min(x0, x1):
            continue
        cur_x = x0 if x0 == x1 else x0 + (pt[1] - y0) * (x1 - x0) / (y1 - y0)
        inside ^= pt[0] > cur_x
    return inside


def isLeft(line, pt, k=1):
    return (k * line.end.lat - k * line.start.lat) * (k * pt.lon - k * line.start.lon) - (k * line.end.lon - k * line.start.lon) * (k * pt.lat - k * line.start.lat)
