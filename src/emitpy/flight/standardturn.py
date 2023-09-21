# Utility functions to smooth turns in flight path
import logging

from math import pi

from emitpy.geo.turf import Point, LineString, Feature, FeatureCollection
from emitpy.geo.turf import destination, bearing, distance
#from .movement import MovePoint

logger = logging.getLogger("standard_turns")


def sign(x):
    return -1 if x < 0 else (0 if x == 0 else 1)


def turnRadius(speed):  # speed in m/s, returns radius in m
    return 120 * speed / (2 * pi)


def turn(bi, bo):
    t = bi - bo
    if t < 0:
        t += 360
    if t > 180:
        t -= 360
    return t


def extend_line(line, pct=40):
    # Extended line direction need to be returned (opposite direction)
    # New  6/2/22: distance to extend is now proportionnal to length of segment.
    # New 25/2/22: ... with a minimum of 20-40 km, because sometimes, segments are very short.
    # We noticed segments can sometimes be as long as 300km
    #
    brng = bearing(Feature(geometry=Point(line["coordinates"][0])), Feature(geometry=Point(line["coordinates"][1])))
    newdist = distance(Feature(geometry=Point(line["coordinates"][0])), Feature(geometry=Point(line["coordinates"][1])))
    dist = max(30, newdist * pct / 100)  # km
    far0 = destination(Feature(geometry=Point(line["coordinates"][0])), dist, brng + 180)
    far1 = destination(Feature(geometry=Point(line["coordinates"][1])), dist, brng)
    return Feature(geometry=LineString([far1["geometry"]["coordinates"], far0["geometry"]["coordinates"]]),
                   properties={
                       "name": f"B {brng}",
                       "bearing": brng
                   })


def line_offset(line, offset):
    p0 = Feature(geometry=Point(line["geometry"]["coordinates"][0]))
    p1 = Feature(geometry=Point(line["geometry"]["coordinates"][1]))
    brg = bearing(p0, p1)
    brg = brg - 90 # sign(offset) * 90
    d0 = destination(p0, offset, brg)
    d1 = destination(p1, offset, brg)
    return Feature(geometry=LineString([d0["geometry"]["coordinates"], d1["geometry"]["coordinates"]]))


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


def line_arc(center, radius, start, end, steps=8):
    arc = []
    if end < start:
        end = end + 360
    step = (end - start) / steps
    a = start
    while a < end:
        p = destination(center, radius, a + 180)
        arc.append(p)
        a = a + step
    return arc


def standard_turn_flyby(l0, l1, radius, precision=8):
    local_debug = False
    b_in = bearing(Feature(geometry=Point(l0["coordinates"][1])), Feature(geometry=Point(l0["coordinates"][0])))
    b_out = bearing(Feature(geometry=Point(l1["coordinates"][1])), Feature(geometry=Point(l1["coordinates"][0])))
    turnAngle = turn(b_in, b_out)

    # Eliminate almost straight turns
    if abs(turnAngle) < 10:
        if local_debug:
            logger.debug(f"standard_turn: small turn, skipping (turn={turnAngle:f}°)")
        return None

    # Eliminate half turns and almost half turns
    if abs(turnAngle) > 150:
        if local_debug:
            logger.debug(f"standard_turn: turn too large, skipping (turn={turnAngle:f}°)")
        return None

    if abs(turnAngle) > 120:
        if local_debug:
            logger.debug(f"standard_turn: large turn (turn={turnAngle:f}°)")

    # Eliminate short segement turns (impossible)
    d_in = distance(Feature(geometry=Point(l0["coordinates"][1])), Feature(geometry=Point(l0["coordinates"][0])))
    d_out = distance(Feature(geometry=Point(l1["coordinates"][1])), Feature(geometry=Point(l1["coordinates"][0])))

    r = 1.5 * radius / 1000  # km
    if d_in < r or d_out < r:
        if local_debug:
            logger.debug(f"standard_turn: segment too small, skipping in={d_in:f} out={d_out:f} (r={r:f}, turn={turnAngle:f}°)")
        return None

    # Here we go
    oppositeTurnAngle = turn(b_out, b_in)

    l0e = extend_line(l0, 20)
    l1e = extend_line(l1, 20)
    cross_ext = line_intersect(l0e, l1e)  # returns a FeatureCollection
    if cross_ext is None:
        # logger.warning("standard_turn: lines do not cross close %s %s" % (l0e, l1e))
        return None

    l0b = line_offset(l0e, sign(oppositeTurnAngle) * radius / 1000)
    l1b = line_offset(l1e, sign(oppositeTurnAngle) * radius / 1000)
    center = line_intersect(l0b, l1b)
    if center is None:
        logger.warning(f"standard_turn: no arc center (turn={turnAngle:f}°)")
        if local_debug:
            logger.debug(f"standard_turn: no arc center ({FeatureCollection(features=[l0b, l1b])})")
        return None

    arc0 = b_out + 90 if turnAngle > 0 else b_in - 90
    arc1 = b_in + 90 if turnAngle > 0 else b_out - 90

    # New 6/2/22: Experimental, more precise
    newradius = distance(cross_ext, center)

    # New 6/2/22: Module number of point with turn
    steps = min(precision, 2 + round(abs(turnAngle / 36)))
    arc = line_arc(center, radius/1000, arc0, arc1, steps)

    if turnAngle > 0:  # reverse coordinates order
        arc.reverse()

    return arc
