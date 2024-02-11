"""
Isolated shapely function calls from other geo based functions.
To make things easier we using shape as dict key, so need to be immutable (& hashable).
So we need shapely > 2.
"""

from shapely.geometry import LineString, Polygon
from shapely.geometry import GeometryCollection, MultiLineString, MultiPoint


def shapeFlight(moves):
    return LineString([f.coords() for f in moves])


def shapeAirspaces(airspaces):
    return dict([(Polygon(f.coords()[0]), f) for f in airspaces])


def airspace_intersects(airspaces, flight: LineString):
    matches = filter(flight.intersects, airspaces.keys())
    return dict([(k, airspaces[k]) for k in matches])


def intersections(polygon, segment):
    a = polygon.intersections(
        segment
    )  # -> linestring or multilinestring or geometrycollection
    if type(a) in [MultiLineString, MultiPoint, GeometryCollection]:
        return list(a.geoms)  # assume collection of points and linestrings
    return [a]
