# Utility functions to smooth turns in flight path
import logging
import io

from math import pi

from emitpy.geo.turf import Point, LineString, Feature, FeatureCollection
from emitpy.geo.turf import destination, bearing, distance
from emitpy.geo import mk360

logger = logging.getLogger("standard_turns")


def sign(x):
    return -1 if x < 0 else (0 if x == 0 else 1)

def turnRadius(speed):  # speed in m/s, returns radius in m for standard turns (2 min)
    return 120 * speed / (2 * pi)

def extend_line(line, pct=40):
    # Extended line direction need to be returned (opposite direction)
    # New  6/2/22: distance to extend is now proportionnal to length of segment.
    # New 25/2/22: ... with a minimum of 20-40 km, because sometimes, segments are very short.
    # We noticed segments can sometimes be as long as 300km
    #
    brng = bearing(line.coordinates[0], line.coordinates[1])
    newdist = distance(line.coordinates[0], line.coordinates[1])
    dist = max(30, newdist * pct / 100)  # km
    far0 = destination(line.coordinates[0], dist, brng + 180)
    far1 = destination(line.coordinates[1], dist, brng)
    return Feature(geometry=LineString([far1.geometry.coordinates, far0.geometry.coordinates]),
                   properties={
                       "name": f"B {brng}",
                       "bearing": brng
                   })

def line_offset(line, offset):
    p0 = line.geometry.coordinates[0]
    p1 = line.geometry.coordinates[1]
    brg = bearing(line.geometry.coordinates[0], line.geometry.coordinates[1])
    brg = brg - 90 # sign(offset) * 90
    d0 = destination(p0, offset, brg)
    d1 = destination(p1, offset, brg)
    return Feature(geometry=LineString([d0.geometry.coordinates, d1.geometry.coordinates]))

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

DEBUG_STANDARD_TURNS = False
# FLY BY
#
#
def standard_turn_flyby(l0, l1, radius, precision: int = 8, soft: bool = False):
    # Soft: Added 25-09-2023.
    # Prevent hard fails, and return "soft" 3-point in-turn-out as output.
    output = io.StringIO()

    def turn(bi, bo):
        t = bi - bo
        if t < 0:
            t += 360
        if t > 180:
            t -= 360
        return t

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

    def report_log(out):
        contents = out.getvalue()
        out.close()
        if DEBUG_STANDARD_TURNS:
            logger.debug(contents)

    print(f"\n{l0}, {l1}, r={radius}", file=output)

    b_in = bearing(l0.coordinates[1], l0.coordinates[0])
    b_out = bearing(l1.coordinates[1], l1.coordinates[0])
    points = [Feature(geometry=Point(l0.coordinates[0]))]
    points.append(Feature(geometry=Point(l0.coordinates[1])))
    points.append(Feature(geometry=Point(l1.coordinates[1])))
    turnAngle = turn(b_in, b_out)

    # Eliminate almost straight turns
    if abs(turnAngle) < 10:
        print(f"small turn, skipping (turn={turnAngle:f}°)", file=output)
        if soft:
            print(f"returning points", file=output)
            return points
        return None

    # Eliminate half turns and almost half turns
    if abs(turnAngle) > 150:
        print(f"turn too large, skipping (turn={turnAngle:f}°)", file=output)
        return None

    if abs(turnAngle) > 120:
        print(f"large turn (turn={turnAngle:f}°)", file=output)

    # Eliminate short segement turns (impossible)
    d_in = distance(l0.coordinates[1], l0.coordinates[0])
    d_out = distance(l1.coordinates[1], l1.coordinates[0])

    r = 1.5 * radius / 1000  # km
    if d_in < r or d_out < r:
        print(f"segment too small, skipping in={d_in:f} out={d_out:f} (r={r:f}, turn={turnAngle:f}°)", file=output)
        if soft:
            print(f"returning points", file=output)
            report_log(output)
            return points
        return None

    # Here we go
    oppositeTurnAngle = turn(b_out, b_in)

    l0e = extend_line(l0, 20)
    l1e = extend_line(l1, 20)
    cross_ext = line_intersect(l0e, l1e)  # returns a FeatureCollection
    if cross_ext is None:
        logger.warning("lines do not cross close %s %s" % (l0e, l1e))
        report_log(output)
        return None

    l0b = line_offset(l0e, sign(oppositeTurnAngle) * radius / 1000)
    l1b = line_offset(l1e, sign(oppositeTurnAngle) * radius / 1000)
    center = line_intersect(l0b, l1b)
    if center is None:
        logger.warning(f"no arc center (turn={turnAngle:f}°)")
        print(f"no arc center ({FeatureCollection(features=[l0b, l1b])})", file=output)
        if soft:
            print(f"returning points", file=output)
            report_log(output)
            return points
        report_log(output)
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


# FLY OVER
#
#
def standard_turn_flyover(l0, l1, radius):
    #
    # Standard turns manipulates angle [0,360[.
    # pyturn manipulates angles [-180, 180]
    #
    # Return None if fails
    #
    output = io.StringIO()

    def new_turn(bi, bo):
        # Return turn angle between [-180, 180] relative to bi,
        # negative angle is counter-clockwise (left) turn
        if bi == bo:
            return 0
        bi = mk360(bi)
        bo = mk360(bo)
        left_turn = None
        angle = 0
        if bo > bi:
            left_turn = False
            angle = bo - bi
        else:
            left_turn = True
            angle = bi - bo
        if angle > 180:
            angle = 360 - angle
            left_turn = not left_turn
        ret = (angle * -1.0) if left_turn else angle
        direct = "counter-clockwise/left" if left_turn else "clockwise/right"
        print(f"turn {direct} {round(angle, 3)} degrees => {round(ret, 3)}", file=output)
        return ret

    def new_line_arc(center, radius, start, end, direction, steps=8):
        print(f"line_arc from heading {start} to {end} ({direction})", file=output)
        start = mk360(start)
        end = mk360(end)
        left_turn = direction < 0
        print(f"line_arc from heading after mk360 {start} to {end} ({left_turn})", file=output)
        arc = []
        if left_turn:
            if start < end:
                start = start + 360
            step = (start - end) / steps
            a = start
            print(f"line_arc left: {start}, {end}, (-) {step}", file=output)
            while a > end:
                p = destination(center, radius, a)
                arc.append(p)
                a = a - step
        else:
            if end < start:
                end = end + 360
            step = (end - start) / steps
            a = start
            print(f"line_arc right: {start}, {end}, (+) {step}", file=output)
            while a < end:
                p = destination(center, radius, a + 180)
                arc.append(p)
                a = a + step
        return arc

    def report_log(out):
        contents = out.getvalue()
        out.close()
        if DEBUG_STANDARD_TURNS:
            logger.debug(contents)

    print(f"\n{l0}, {l1}, r={radius}", file=output)

    p_start = Feature(geometry=Point(l0.coordinates[0]))
    p_turn = Feature(geometry=Point(l0.coordinates[1]))
    p_end = Feature(geometry=Point(l1.coordinates[1]))
    b_in = bearing(p_start, p_turn)
    b_out = bearing(p_turn, p_end)

    # Basic checks and exclusion of border cases
    r = 1.5 * radius / 1000
    d_in = distance(p_start, p_turn, units="km")
    d_out = distance(p_turn, p_end, units="km")
    if d_in < r or d_out < r:
        print(f"segment too small l_in={round(d_in, 3)}, l_out={round(d_out, 3)}km (r={radius})", file=output)
        report_log(output)
        return None

    turnAngle = new_turn(b_in, b_out)
    # Eliminate almost straight turns
    if abs(turnAngle) < 10:
        print(f"small turn, skipping (turn={turnAngle:f}°)", file=output)
        report_log(output)
        return None

    turnAngleExtra = min(turnAngle * 1.5, 180)
    b_out_old = b_out
    b_out = b_in + turnAngleExtra
    print(f"b_in={b_in}, b_out: {b_out_old}, turn={turnAngle}, extra={turnAngleExtra}, new_b_out: {b_out}", file=output)

    # angle vertex
    r = radius / 1000
    v = Feature(geometry=Point(l0.coordinates[1]))
    c1 = destination(v, r, b_in + sign(turnAngle) * 90)
    arc1 = new_line_arc(c1, r, b_in+90, b_out+90, sign(turnAngle), 8)
    if arc1 is None or len(arc1) == 0:
        logger.warning(f"no arc 1")
        report_log(output)
        return None

    # from the last point, we draw a line to intersect the outline:
    straight = destination(arc1[-1], 20*radius, b_out)
    l2 = Feature(geometry=LineString([arc1[-1].geometry.coordinates, straight.geometry.coordinates]))
    intersect = line_intersect(Feature(geometry=l1), l2)
    if intersect is None:
        logger.warning("no intersect")
        report_log(output)
        return None
    join = LineString([arc1[-1].geometry.coordinates, intersect.geometry.coordinates])
    left = LineString([intersect.geometry.coordinates, l1.coordinates[1]])
    arc2 = standard_turn_flyby(join, left, radius, soft=True)
    if arc2 is None:
        logger.warning(f"no arc 2")
        report_log(output)
        return None

    ret = arc1 + arc2
    return ret
