from geojson import Point, Feature, FeatureCollection
from turfpy.measurement import distance, nearest_point

p0 = Point((25.0, 51.0))


p1 = Point((25.2, 51.2))
f1 = Feature(geometry=p1)
p2 = Point((25.4, 51.6))
f2 = Feature(geometry=p2)

print("to p1", distance(p0, p1))
# to p1 26.260267785645777

print("to p2", distance(p0, p2))
# to p2 72.28066331033915

fc1 = FeatureCollection(features=[f1, f2])
print("to p1", nearest_point(p0, fc1))
# to p1 {"geometry": {"coordinates": [25.2, 51.2], "type": "Point"}, "properties": {"distanceToPoint": 26.260267785645777, "featureIndex": 0}, "type": "Feature"}

fc2 = FeatureCollection(features=[f2, f1])
print("to p2", nearest_point(p0, fc2))
# to p2 {"geometry": {"coordinates": [25.4, 51.6], "type": "Point"}, "properties": {"distanceToPoint": 72.28066331033915, "featureIndex": 0}, "type": "Feature"}