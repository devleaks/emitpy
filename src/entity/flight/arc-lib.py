"""
Make arcs for standard turns
"""

from math import pi
from geojson import Feature, FeatureCollection, Point, LineString
from turfpy.measurement import distance

# Extends a line be dist kilometers at both ends.
def extendLine(line, dist=20):
    bearing = bearing(line.geometry.coordinates[0], line.geometry.coordinates[1])
    far0 = destination(line.geometry.coordinates[1], dist, bearing)
    far1 = destination(line.geometry.coordinates[0], dist, bearing + 180)
    return Feature(geometry=LineString([far0.geometry.coordinates, far1.geometry.coordinates]),
                   properties={
                    "name": "B " + bearing,
                    "bearing": bearing
                   })

#  Utility 	def to adjust parallel to required precision with maximum count iterations.
def notSame(line):
    return ((line.geometry.coordinates[0][0] != line.geometry.coordinates[1][0]) or
            (line.geometry.coordinates[0][1] != line.geometry.coordinates[1][1]))


def adjustLineOffset(line, offset, precision, count):
    offs = abs(offset)
    soffset = sign(offset)
    #  logger.debug("adjustLineOffset", line.geometry.coordinates)
    diff = offset
    while (--count > 0 and abs(diff) > precision and notSame(line)):
        newline = lineOffset(line, soffset * offs)
        diff = abs(offset) - distance(line.geometry.coordinates[0], newline.geometry.coordinates[0])
        diff_e = abs(offset) - distance(line.geometry.coordinates[1], newline.geometry.coordinates[1])
        diff = (diff + diff_e) / 2
        offs = offs + 0.5 * diff
    #  logger.debug(">",count, diff)
    return soffset * offs


def lineOffset(line, offset):
    newr = adjustLineOffset(line, offset, 0.001, 20)  # 1m, 10 iterations
    l1 = lineOffset(line, newr) if notSame(line) else line
    return extendLine(l1)


# Returns turn angle between bearing in and bearing out, positive for left turn, negative for right turns.
# Can only turn up to 179°, left or right. No 240° turns.
def turn(bi, bo):
    t = bi - bo
    if t < 0:
        t = t + 360
    if t > 180:
        t = t - 360
    return t


#  returns arc center, always "inside" both lines l0 and l1
def arcCenter(l0, l1, radius):
    b_in = bearing(l0.geometry.coordinates[0], l0.geometry.coordinates[1])
    b_out = bearing(l1.geometry.coordinates[0], l1.geometry.coordinates[1])
    turnAngle = turn(b_in, b_out)
    oppositeTurnAngle = turn(b_out, b_in)
    l0b = lineOffset(l0, sign(turnAngle) * radius) #  offset line is always on right side of line
    l1b = lineOffset(l1, sign(oppositeTurnAngle) * radius)

    intersects = lineIntersect(l0b, l1b)
    center = intersects.features[0] if (intersects.features.length > 0) else False
    if not center:
        logger.warning("no center found", l0, l1)

    return center


# Compute turn radius in km given airplane speed in km/h.
# Standard turn is 360° turns in 2 minutes.
def turnRadius(speed=463):  # km/h = 250kn
    return speed / (60 * pi)  #  km


# Returns arc with supplied radius joining segment l0 and l1.
# Arc property 'reverse' set to True or False if arc was from l1 to l0.
def mkturn(l0, l1, radius, steps=64):
    b_in = bearing(l0.geometry.coordinates[0], l0.geometry.coordinates[1])
    b_out = bearing(l1.geometry.coordinates[0], l1.geometry.coordinates[1])
    turnAngle = turn(b_in, b_out)
    oppositeTurnAngle = turn(b_out, b_in)

    #  logger.debug("mkturn: bearings from to turn revturn", b_in, b_out, turnAngle, oppositeTurnAngle)
    #  where the two line crosses
    l0e = extendLine(l0, 20)
    l1e = extendLine(l1, 20)
    cross_arr = lineIntersect(l0e, l1e)
    cross = cross_arr.features[0] if (cross_arr.features.length > 0) else False
    if not cross:
        logger.warning("mkturn: lines do not cross close", l0e, l1e)
        return False

    #  arc center
    l0b = lineOffset(l0, sign(oppositeTurnAngle) * radius)
    """
    addProps(l0b,:
        "stroke": "#ff0000",
        "stroke-width": 1,
        "stroke-opacity": 1
    )
    fc.append(copy(l0b))
    """
    l1b = lineOffset(l1, sign(oppositeTurnAngle) * radius)
    """
    addProps(l1b,:
        "stroke": "#00ff00",
        "stroke-width": 1,
        "stroke-opacity": 1
    )
    fc.append(copy(l1b))
    """

    intersects = lineIntersect(l0b, l1b)
    center = intersects.features[0] if intersects.features.length > 0 else False
    if not center:
        logger.warning("mkturn: no arc center found", l0, l1)
        return False

    #  arc
    arc0 = b_out + 90 if turnAngle > 0 else b_in - 90
    arc1 = b_in + 90 if turnAngle > 0 else b_out - 90
    arc = lineArc(center, radius, arc0, arc1, {"steps": steps})

    if turnAngle > 0:  # reverse coordinates order
        arc.geometry.coordinates = arc.geometry.coordinates.reverse()

    return arc


"""
# Add smooth turn between each segment
 *
# @param     :<type>  f      : original linestring coordinates and *AtVertices interpolated.
# @return    :<type> :  A new LisString Feature with all smooth turns and adjusted original *AtVertices.
 """
def smoothTurns(ls):
    newls = []
    newidxs = []
    hadarc = False

    def add(old, addToLS=True):
        newidx = len(newls)  # length after push - 1
        newidxs.append({
            "old": old,
            "new": newidx
        })
        if addToLS:
            newls.append(ls[old])

    add(0)  # first point

    for i in range(1, len(ls)):
        li = Feature(LineString([ls[i - 1], ls[i]]))
        lo = Feature(LineString([ls[i], ls[i + 1]]))
        #  logger.debug("smoothTurns", i, alts[i], speeds[i])
        arc = mkturn(li, lo, turnRadius(speeds[i]))
        if arc is not None:  # speed and alt will be interpolated during arc
            #  logger.debug("doing arc..", i, newls.length)
            add(i, False)  #  add speed, alt, pause... at start of arc, but do not add point
                           #  could add at end of arc, ideally middle of arc...
            arc.geometry.coordinates.forEach(c => newls.append(c))
            # logger.debug("..done arc", i, newls.length)
            hadarc = True
         else:
            add(i, not hadarc) # add speed, alt, pause, but do not add point
            hadarc = False     # to the linestring because it was "by passed" by smooth turn
     else:
        add(i)



    add(ls.length - 1)  # last point

    return Feature(geometry=LineString(newls))
