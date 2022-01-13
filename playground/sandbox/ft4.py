from geojson import Point, LineString

class Line(LineString):

    def __init__(self, start: Point, end: Point, width: float=None):
        LineString.__init__(self, ((start.coordinates, end.coordinates)))
        self.start = start
        self.end = end
        self.width = width

l = Line(start=Point((1.0, 1.0)), end=Point((1.0, 2.0)), width=1.0)
print(isinstance(l, LineString))
#True
print(l)
#{"coordinates": [[1.0, 1.0], [1.0, 2.0]], "end": {"coordinates": [1.0, 2.0], "type": "Point"}, "start": {"coordinates": [1.0, 1.0], "type": "Point"}, "type": "Line", "width": 1.0}