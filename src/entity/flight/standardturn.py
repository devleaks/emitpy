import logging

from math import pi

from geojson import Point, LineString, Feature, FeatureCollection
from turfpy.measurement import distance, destination
from turfpy.misc import line_intersect, line_arc
from turfpy.transformation import line_offset

from ..geo import Segment

logger = logging.getLogger("smoothTurns")

def turnRadius(speed):  # speed in m/s, returns radius in m
    return 120 * speed / (2 * pi)


def turn(bi, bo):
    t = bi - bo
    if t < 0:
        t += 360
    if t > 180:
        t -= 360
    return t

def sign(x):
    return -1 if x < 0 else (0 if x == 0 else 1)

def extendLine(line, dist=20):
    brng = line.bearing()
    far0 = destination(line["geometry"]["coordinates"][1], dist, brng)
    far1 = destination(line["geometry"]["coordinates"][0], dist, brng + 180)
    return Feature(geometry=LineString([far0["geometry"]["coordinates"], far1["geometry"]["coordinates"]]),
                   properties={
                    "name": "B " + brng,
                    "bearing": brng
                   })


def standard_turn(l0, l1, radius, steps: int = 64):
    b_in = l0.bearing()
    b_out = l1.bearing()
    turnAngle = turn(b_in, b_out)
    oppositeTurnAngle = turn(b_out, b_in)

    l0e = extendLine(l0, 20)
    l1e = extendLine(l1, 20)
    cross_arr = line_intersect(l0e, l1e)  # returns a FeatureCollection
    if (cross_arr is None) or (len(cross_arr.features) == 0):
        logger.warning("mkturn: lines do not cross close %s %s" % (l0, l1))
        return None

    l0b = line_offset(l0, sign(oppositeTurnAngle) * radius)
    l1b = line_offset(l1, sign(oppositeTurnAngle) * radius)

    intersects = line_intersect(l0b, l1b)

    if (intersects is None) or (len(intersects.features) == 0):
        logger.warning("mkturn: no arc center found %s %s" % (l0, l1))
        return None

    center = intersects.features[0]

    arc0 = b_out + 90 if turnAngle > 0 else b_in - 90
    arc1 = b_in + 90 if turnAngle > 0 else b_out - 90

    arc = line_arc(center, radius, arc0, arc1, {"steps": steps})

    if turnAngle > 0:  # reverse coordinates order
        arc["geometry"]["coordinates"].reverse()

    return arc


def standard_turns(arrin):
    arrout = []
    last_speed = None
    arrout.append(arrin[0])

    for i in range(1, len(arrin) - 1):
        print(">>>", arrin[i-1]["geometry"], arrin[i-1]["geometry"]["coordinates"])
        li = Segment(start=arrin[i-1]["geometry"], end=arrin[i]["geometry"])
        lo = Segment(start=arrin[i]["geometry"], end=arrin[i+1]["geometry"])
        s = arrin[i].speed()
        if s is None:
            s = last_speed
        arc = standard_turn(li, lo, turnRadius(s))
        last_speed = s

        if arc is not None:
            arrout.append(arrin[i])
            for p in arc:
                arrout.append(p)
        else:
            arrout.append(arrin[i])

    return arrout