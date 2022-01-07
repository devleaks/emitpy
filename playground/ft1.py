from geojson import Point, Feature
from turfpy.measurement import distance

class Vertex(Feature):
    def __init__(self, node: str, point: Point):
        Feature.__init__(self, geometry=point)
        self.name = node

p1 = Point((25.25458, 51.623879))
f1 = Feature(geometry=p1)
v1 = Vertex("v1", point=p1)
p2 = Point((25.254626, 51.624053))
f2 = Feature(geometry=p2)
v2 = Vertex("v2", point=p2)

dp = distance(p1, p2)
print("dp: ",dp)  # df:  0.019606799666682842

df = distance(f1, f2)
print("df: ",df)  # df:  0.019606799666682842

print("v1 is feature?", isinstance(v1, Feature))  # true

dv1 = distance(v1.geometry, v2.geometry)
print("dv1: ",dv1)  # df:  0.019606799666682842


dv = distance(v1, v2)
print("dv: ", dv)
# Error:
# Traceback (most recent call last):
#   File "/Users/pierre/Developer/Internet/js/gip/emitpy/tests/ft.py", line 19, in <module>
#     dv = distance(v1, v2)
#   File "/usr/local/miniconda3/lib/python3.9/site-packages/turfpy/measurement.py", line 112, in distance
#     coordinates1 = get_coord(point1)
#   File "/usr/local/miniconda3/lib/python3.9/site-packages/turfpy/helper.py", line 80, in get_coord
#     raise Exception("coord must be GeoJSON Point or an Array of numbers")
# Exception: coord must be GeoJSON Point or an Array of numbers