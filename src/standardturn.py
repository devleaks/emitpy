import logging

from math import pi, cos, acos, sin

from geojson import Point, LineString, Feature, FeatureCollection
from turfpy.measurement import destination, bearing, distance

logger = logging.getLogger("standard_turns")

ARRINPUT = []

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
    print("line offset", offset, sign(offset), brg)
    d0 = destination(p0, offset, brg)
    # print("d0", distance(d0, p0), offset)
    d1 = destination(p1, offset, brg)
    # print("d1", distance(d1, p1), offset)
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


def color(f, c):
    f["properties"]["marker-color"] = c
    f["properties"]["marker-size"] = "medium"
    f["properties"]["marker-symbol"] = ""


def color_all(arr, c):
    for f in arr:
        color(f, c)


def standard_turn_flyby(l0, l1, radius):
    b_in = bearing(Feature(geometry=Point(l0["coordinates"][1])), Feature(geometry=Point(l0["coordinates"][0])))
    b_out = bearing(Feature(geometry=Point(l1["coordinates"][1])), Feature(geometry=Point(l1["coordinates"][0])))
    turnAngle = turn(b_in, b_out)
    oppositeTurnAngle = turn(b_out, b_in)
    print(">>>angles", b_in, b_out, turnAngle, oppositeTurnAngle)

    l0e = extend_line(l0, 20)
    l1e = extend_line(l1, 20)
    cross_ext = line_intersect(l0e, l1e)  # returns a FeatureCollection
    # print(">>>extend_line")
    # print(FeatureCollection(features=ARRINPUT + [l0e, l1e]))
    # print(">>>cross_ext", cross_ext)
    if cross_ext is None:
        logger.warning("standard_turn: lines do not cross close %s %s" % (l0e, l1e))
        print(">>>extend_line")
        print(FeatureCollection(features=ARRINPUT + [l0e, l1e]))
        print(">>>cross_ext", cross_ext)
        return None
    color(cross_ext, "#ff0000")

    l0b = line_offset(l0e, sign(oppositeTurnAngle) * radius / 1000)
    l1b = line_offset(l1e, sign(oppositeTurnAngle) * radius / 1000)
    center = line_intersect(l0b, l1b)

    # print(">>>line_offset")
    # print(FeatureCollection(features=ARRINPUT + [l0b, l1b, center]))
    if center is None:
        logger.warning("standard_turn: no arc center %s %s" % (l0, l1))
        return None

    color(center, "#00ff00")
    print(">>>Control", radius/1000, distance(cross_ext, center))

    arc0 = b_out + 90 if turnAngle > 0 else b_in - 90
    arc1 = b_in + 90 if turnAngle > 0 else b_out - 90
    newradius = distance(cross_ext, center)
    print(">>>arc", arc0, arc1, radius/1000, newradius)


    # New: Module number of point with turn
    steps = 4 + round(abs(turnAngle / 36))
    arc = line_arc(center, radius/1000, arc0, arc1, steps)
    color_all(arc, "#00ffff")
    # print(FeatureCollection(features=arc))
    print(">>>ALL", b_in, b_out, radius/1000, arc0, arc1, len(arc))
    print(FeatureCollection(features=ARRINPUT + [l0e, l1e, l0b, l1b, cross_ext, center] + arc))

    if turnAngle > 0:  # reverse coordinates order
        arc.reverse()

    return arc


def standard_turn_flyover(l0, l1, r):
    b_in = bearing(Feature(geometry=Point(l0["coordinates"][1])), Feature(geometry=Point(l0["coordinates"][0])))
    b_out = bearing(Feature(geometry=Point(l1["coordinates"][1])), Feature(geometry=Point(l1["coordinates"][0])))
    turnAngle = turn(b_in, b_out)
    oppositeTurnAngle = turn(b_out, b_in)
    print(">>>angles", b_in, b_out, turnAngle, oppositeTurnAngle)

    radius = r / 1000
    # angle vertex
    v = Feature(geometry=Point(l0["coordinates"][1]))

    ta = turnAngle * pi / 180  # π radians
    h = radius * (1 - cos(ta / 2))

    h2 = h / 2
    tb = acos( 1 - (h2/radius)) * 180 / pi
    beta = 2 * tb  # degrees
    gamma = beta + (turnAngle - beta) / 2
    gamma = gamma + 14

    l = abs(2 * radius * sin(ta/2))

    print(">>>calcul", beta, gamma, radius, h, l)

    c1 = destination(v, radius, b_in - 90)

    ext2 = destination(v, radius, b_out + 90)
    c2 = destination(ext2, 2 * l, b_out + 180)
    tangent = gamma + 90
    # arc for turn
    s1 = b_in-90
    e1 = tangent+90
    if s1 > e1:
        s1, e1 = e1, s1
    arc1 = line_arc(c1, radius, s1, e1, 8)
    color_all(arc1, "#FF0000")

    # from the last point, we draw a line to intersect the outline:
    straight = destination(arc1[-1], 10*radius, e1)
    l2 = Feature(geometry=LineString([arc1[-1]["geometry"]["coordinates"],straight["geometry"]["coordinates"]]))
    intersect = line_intersect(Feature(geometry=l1), l2)
    color(intersect, "#DDFFDD")
    join = LineString([arc1[-1]["geometry"]["coordinates"],intersect["geometry"]["coordinates"]])

    arc2 = standard_turn_flyby(l1, join, r)
    if arc2 is not None:
        color_all(arc2, "#00FF00")
    else:
        arc2 = []

    color(c1, "#000000")
    color(c2, "#FFFFFF")
    color(ext2, "#888888")

    return [c1] + arc1 + arc2


def standard_turn_flyover2(l0, l1, r):
    b_in = bearing(Feature(geometry=Point(l0["coordinates"][1])), Feature(geometry=Point(l0["coordinates"][0])))
    b_out = bearing(Feature(geometry=Point(l1["coordinates"][1])), Feature(geometry=Point(l1["coordinates"][0])))
    turnAngle = turn(b_in, b_out)
    oppositeTurnAngle = turn(b_out, b_in)
    print(">>>angles", b_in, b_out, turnAngle, oppositeTurnAngle)

    radius = r / 1000
    # angle vertex
    v = Feature(geometry=Point(l0["coordinates"][1]))

    ta = turnAngle * pi / 180  # π radians
    h = radius * (1 - cos(ta / 2))

    h2 = h / 2
    tb = acos( 1 - (h2/radius)) * 180 / pi
    beta = 2 * tb  # degrees
    gamma = beta + (turnAngle - beta) / 2
    gamma = gamma + 14

    l = abs(2 * radius * sin(ta/2))

    print(">>>calcul", beta, gamma, radius, h, l)

    c1 = destination(v, radius, b_in - 90)

    ext2 = destination(v, radius, b_out + 90)
    c2 = destination(ext2, 2 * l, b_out + 180)
    tangent = gamma + 90
    # arc for turn
    s1 = b_in-90
    e1 = tangent+90
    if s1 > e1:
        s1, e1 = e1, s1
    arc1 = line_arc(c1, radius, s1, e1, 8)
    color_all(arc1, "#FF0000")

    # arc for back-on-track
    s2 = tangent-90
    e2 = b_out+90
    if s2 > e2:
        s2, e2 = e2, s2
    arc2 = line_arc(c2, radius, s2, e2, 8)
    color_all(arc2, "#00FF00")


    color(c1, "#000000")
    color(c2, "#FFFFFF")
    color(ext2, "#888888")

    return [ext2, c1, c2] + arc1 + arc2


def standard_turns(arrin):
    global ARRINPUT
    ARRINPUT = arrin
    color_all(ARRINPUT, "#ffff00")
    arrout = []
    last_speed = 100
    arrout.append(arrin[0])

    print("START", len(arrin), turnRadius(last_speed))
    for i in range(1, len(arrin) - 1):
        li = LineString([arrin[i-1]["geometry"]["coordinates"], arrin[i]["geometry"]["coordinates"]])
        lo = LineString([arrin[i]["geometry"]["coordinates"], arrin[i+1]["geometry"]["coordinates"]])
        s = last_speed  # arrin[i].speed()
        if s is None:
            s = last_speed
        arc = standard_turn_flyover(li, lo, turnRadius(s))
        last_speed = s

        if arc is not None:
            arrout.append(arrin[i])
            # color(arc[0], "#ff0000")
            for p in arc:
                arrout.append(p)
        else:
            arrout.append(arrin[i])
        print("---------------------")

    return arrout
