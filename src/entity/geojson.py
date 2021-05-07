# Geographic geometry utility functions
# (I tested geo-py but precision was inferior(?).)

import json


class Marker:
    # geojsonio
    def __init__(self, marker, markerColor, markerSize):
        self.marker = marker
        self.markerColor = markerColor
        self.markerSize = markerSize


class Segment:
    # geojsonio
    def __init__(self, stroke, strokeWidth, strokeOpacity):
        self.stroke = stroke
        self.strokeWidth = strokeWidth
        self.strokeOpacity = strokeOpacity


class Geometry:
    def __init__(self, gtype, coordinates):
        self.type = gtype
        self.coordinates = coordinates

    def geometry(self):
        return {
            "type": self.type,
            "coordinates": self.coordinates
        }

    def __str__(self):
        return json.dumps(self.geometry())



class Feature:
    def __init__(self, gtype, geometry, properties={}):
        self.type = "Feature"
        self.geometry = geometry
        self.properties = properties

    def feature(self):
        return {
            "type": "Feature",
            "geometry": self.geometry(),
            "properties": self.properties
        }

    def __str__(self):
        return json.dumps(self.feature())


class Point(Marker, Geometry):
    def __init__(self, lat, lon, alt=None, marker=None, markerColor="#aaaaaa", markerSize="medium"):
        Marker.__init__(self, marker, markerColor, markerSize)
        coordinates = [lon, lat]
        self.lat = lat
        self.lon = lon
        if alt:
            coordinates.append(alt)
        Geometry.__init__(self, "Point", coordinates)

    # def lat(self):
    #     return self.coordinates[1]

    # def lon(self):
    #     return self.coordinates[0]

    def properties(self):
        return {
            "marker-color": self.markerColor,
            "marker-size": self.markerSize
        }

    def geomJSON(self):
        return json.dumps(self.geom())

    def featureJSON(self):
        return json.dumps(self.feature())

    def __str__(self):
        return self.featureJSON()


class LineString(Segment, Geometry):
    # Created from 2 Points
    def __init__(self, pstart, pend, stroke="#aaaaaa", strokeWidth=1, strokeOpacity=1):
        super(Marker, self).__init__(marker, markerColor, markerSize)
        super(Geometry, self).__init__("LineString", [pstart.coordinates, pend.coordinates])

    def lat(self):
        return self.coordinates[1]

    def lon(self):
        return self.coordinates[0]

    def geom(self):
        return {
            "type": "LineString",
            "coordinates": [[self.start.lon, self.start.lat], [self.end.lon, self.end.lat]]
        }

    def feature(self):
        return {
            "type": "Feature",
            "geometry": self.geom(),
            "properties": {
                "stroke": self.stroke,
                "stroke-width": self.strokeWidth,
                "stroke-opacity": self.strokeOpacity
            }
        }

    def geomJSON(self):
        return json.dumps(self.geom())

    def featureJSON(self):
        return json.dumps(self.feature())

    def __str__(self):
        return self.featureJSON()


class FeatureCollection:
    def __init__(self, features=[]):
        self.features = features

    def featureCollection(self):
        return {
            "type": "FeatureCollection",
            "features": self.features
        }

    def featureCollectionJSON(self):
        return json.dumps(self.featureCollection())

    def __str__(self):
        return self.featureCollectionJSON()
