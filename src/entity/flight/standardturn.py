import logging

from math import pi

from geojson import Point, LineString, Feature
from turfpy.measurement import destination, bearing, distance
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
    # New 6/2/22: distance to extend is now proportionnal to length of segment.
    # We noticed segments can sometimes be as long as 300km
    #
    brng = bearing(Feature(geometry=Point(line["coordinates"][0])), Feature(geometry=Point(line["coordinates"][1])))
    newdist = distance(Feature(geometry=Point(line["coordinates"][0])), Feature(geometry=Point(line["coordinates"][1])))
    dist = newdist * pct / 100
    far0 = destination(Feature(geometry=Point(line["coordinates"][0])), dist, brng + 180, {"units": "km"})
    far1 = destination(Feature(geometry=Point(line["coordinates"][1])), dist, brng, {"units": "km"})
    return Feature(geometry=LineString([far1["geometry"]["coordinates"], far0["geometry"]["coordinates"]]),
                   properties={
                    "name": "B %f" % brng,
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


def standard_turn_flyby(l0, l1, radius):
    b_in = bearing(Feature(geometry=Point(l0["coordinates"][1])), Feature(geometry=Point(l0["coordinates"][0])))
    b_out = bearing(Feature(geometry=Point(l1["coordinates"][1])), Feature(geometry=Point(l1["coordinates"][0])))
    turnAngle = turn(b_in, b_out)
    oppositeTurnAngle = turn(b_out, b_in)

    l0e = extend_line(l0, 20)
    l1e = extend_line(l1, 20)
    cross_ext = line_intersect(l0e, l1e)  # returns a FeatureCollection
    if cross_ext is None:
        logger.warning("standard_turn: lines do not cross close %s %s" % (l0e, l1e))
        return None

    l0b = line_offset(l0e, sign(oppositeTurnAngle) * radius / 1000)
    l1b = line_offset(l1e, sign(oppositeTurnAngle) * radius / 1000)
    center = line_intersect(l0b, l1b)
    if center is None:
        logger.warning("standard_turn: no arc center %s %s" % (l0, l1))
        return None

    arc0 = b_out + 90 if turnAngle > 0 else b_in - 90
    arc1 = b_in + 90 if turnAngle > 0 else b_out - 90

    # New 6/2/22: Experimental, more precise
    newradius = distance(cross_ext, center)

    # New 6/2/22: Module number of point with turn
    steps = 4 + round(abs(turnAngle / 36))
    arc = line_arc(center, radius/1000, arc0, arc1, steps)

    if turnAngle > 0:  # reverse coordinates order
        arc.reverse()

    return arc


def standard_turns(arrin):
    arrout = []
    last_speed = 100
    arrout.append(arrin[0])

    for i in range(1, len(arrin) - 1):
        li = LineString([arrin[i-1]["geometry"]["coordinates"], arrin[i]["geometry"]["coordinates"]])
        lo = LineString([arrin[i]["geometry"]["coordinates"], arrin[i+1]["geometry"]["coordinates"]])
        s = last_speed  # arrin[i].speed()
        if s is None:
            s = last_speed
        arc = standard_turn_flyby(li, lo, turnRadius(s))
        last_speed = s

        if arc is not None:
            arrout.append(arrin[i])
            for p in arc:
                arrout.append(p)
                # arrout.append(MovePoint(geometry=p["geometry"], properties=p["properties"]))
        else:
            arrout.append(arrin[i])

    return arrout
