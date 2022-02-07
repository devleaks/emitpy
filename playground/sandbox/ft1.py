from geojson import Point, Feature
from turfpy.measurement import distance

class Vertex(Feature):
    def __init__(self, node: str, point: Point):
        Feature.__init__(self, geometry=point)
        self.name = node


class Ramp(Feature):

    def __init__(self, name: str, ramptype: str, position: [float], orientation: float, use: str):
        Feature.__init__(self, geometry=Point(position), properties={
            "type": "ramp",
            "sub-type": ramptype,
            "use": use,
            "orientation": orientation,
            "available": None})

    def busy(self):
        self.properties["available"] = False

    def available(self):
        self.properties["available"] = True

    def isAvailable(self):
        if "available" in self.properties:
            return self.properties["available"]
        return None

    def addProp(self, propname, propvalue):
        self.properties[propname] = propvalue



p1 = Point((51.623879, 25.25458))
f1 = Feature(geometry=p1)
v1 = Vertex("v1", point=p1)
p2 = Point((51.624053, 25.254626))
f2 = Feature(geometry=p2)
v2 = Vertex("v2", point=p2)

dp = distance(p1, p2)
print("dp: ",dp)  # df:  0.019606799666682842

df = distance(f1, f2)
print("df: ",df)  # df:  0.019606799666682842

print("v1 is feature?", isinstance(v1, Feature))  # true

dv1 = distance(v1.geometry, v2.geometry)
print("dv1: ",dv1)  # df:  0.019606799666682842


r1 = Ramp("R", "T", [51.607392, 25.285817], 180, "all")

dv1 = distance(v1.geometry, v2.geometry)
print("dv1: ",dv1)  # df:  0.019606799666682842

dv2 = distance(r1.geometry, v2.geometry)
print("dv2: ",dv2)  # df:  0.019606799666682842



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