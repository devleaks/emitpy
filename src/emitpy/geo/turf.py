# Wrapper around mig python missing geo library
# No library is satisfying...
# Inconsistencies, missing functions, errors, wrong GeoJSON handling...
#
from turfpy.measurement import distance as turf_distance
from turfpy.measurement import destination as turf_destination
from turfpy.measurement import bearing as turf_bearing
from turfpy.measurement import bbox as turf_bbox
from turfpy.measurement import boolean_point_in_polygon as turf_boolean_point_in_polygon
from turfpy.measurement import point_to_line_distance as turf_point_to_line_distance
from turfpy.misc import line_intersect as turf_line_intersect


# Measures
def distance(p1, p2, units: str = "km"):
    return turf_distance(p1, p2, units)

def point_to_line_distance(point, line):
    return turf_point_to_line_distance(point, line)

def bearing(p1, p2):
    return turf_bearing(p1, p2)

def bbox(p1, p2):
    return turf_bbox(p1, p2)

# Move
def destination(start, length, course, units: str = "km"):
    return turf_destination(start, length, course, {"units": units})

# Checks
def point_in_polygon(point, polygon):
    return turf_boolean_point_in_polygon(point, polygon)

def line_intersect_polygon(line, polygon) -> int:
    # Returns number of intersecting points
    res = turf_line_intersect(line, polygon)
    if res is not None:
        fc = res.get("features")
        if fc is not None:
            return len(fc)  # number of intersecting points
    return 0
