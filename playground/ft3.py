from geojson import Point, LineString, Feature
from turfpy.measurement import point_to_line_distance

class Edge(Feature):
    def __init__(self, node: str, start: Feature, end: Feature):
        Feature.__init__(self, geometry=LineString((start["geometry"]["coordinates"], end["geometry"]["coordinates"])))
        self.name = node

p1 = Point((25.25458, 51.623879))
f1 = Feature(geometry=p1)
p2 = Point((25.254626, 51.624053))
f2 = Feature(geometry=p2)

e1 = Edge("e1", start=f1, end=f2)

p0 = Point((25.0, 51.0))
f0 = Feature(geometry=p0)


fline = Feature(geometry=LineString((f1["geometry"]["coordinates"], f2["geometry"]["coordinates"])))
print(point_to_line_distance(f0, fline))
#71.59329853730718


fedge = Edge(node="e1", start=f1, end=f2)
print(isinstance(fedge, Feature))
#True
print(point_to_line_distance(f0, fedge))
# Traceback (most recent call last):
#   File "/Users/pierre/Developer/Internet/js/gip/emitpy/tests/ft3.py", line 28, in <module>
#     print(point_to_line_distance(f0, fedge))
#   File "/usr/local/miniconda3/lib/python3.9/site-packages/turfpy/measurement.py", line 1004, in point_to_line_distance
#     feature_of(line, "LineString", "line")
#   File "/usr/local/miniconda3/lib/python3.9/site-packages/turfpy/helper.py", line 120, in feature_of
#     raise Exception(
# Exception: Invalid input to line, Feature with geometry required
