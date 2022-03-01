from geojson import Point, Feature

class Vertex(Feature):
    def __init__(self, arr: [float]):
        Feature.__init__(self, geometry=Point(arr))

v = Vertex((1, 2))

print(isinstance(v, Feature), v)
# True {"geometry": {"coordinates": [1, 2], "type": "Point"}, "properties": {}, "type": "Vertex"}
# type="Vertex" is invalid geojson
#


class Edge(Feature):
    def __init__(self, arr: [float]):
        self["type"] = "Feature"
        Feature.__init__(self, geometry=Point(arr))

e = Edge((1, 2))

print(isinstance(e, Feature), e)
