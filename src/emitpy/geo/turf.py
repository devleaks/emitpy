# Wrapper around python missing geo library
# No library is satisfying...
# Inconsistencies, missing functions, errors, wrong GeoJSON handling...
# including errors (e.g. geojson polygons)
#
# _Feature = Feature as used by the base geo package
# Feature = Feature as simple as possible BUT with EmitPy interface, just changing __init__ really.
# FeatureWithProps = Feature with access functions and shortcuts
#
import copy
import inspect
import json
from enum import Enum
from types import NoneType

from jsonpath import JSONPath

from turf.helpers import Point, LineString, Polygon, FeatureCollection
from turf.helpers import Feature as _Feature

#
from turf import distance as turf_distance
from turf import destination as turf_destination
from turf import bearing as turf_bearing
from turf import bbox as turf_bbox
from turf import boolean_point_in_polygon as turf_boolean_point_in_polygon
from turf import point_to_line_distance as turf_point_to_line_distance
from turf import line_intersect as turf_line_intersect

import emitpy
from emitpy.constants import FEATPROP, TAG_SEP


class Feature(_Feature):
    # When emitpy uses a s simple GeoJSON Feature, it uses this one:
    # Which is the package's Feature with 3 functions to get geometry, properties, and coordinates
    # Emitpy should never use the package Feature directly.
    #
    def __init__(self, geometry, properties: dict = {}, **extra):
        _Feature.__init__(self, geom=geometry, properties=properties)  # Feature as defined in pyturf
        self.id = extra.get("id")


class EmitpyFeature(Feature):
    """
    A EmitpyFeature is a GeoJSON Feature<Point> (mainly) with facilities to set a few standard
    properties like altitude, speed, vertical speed and properties.
    It can also set colors for geojson.io map display.
    Altitude is stored in third geometry coordinates array value:

    An OPTIONAL third-position element SHALL be the height in meters above or below the WGS 84 reference ellipsoid.
    (https://datatracker.ietf.org/doc/rfc7946/?include_text=1)
    """

    def __init__(self, geometry, properties={}, **extra):
        Feature.__init__(self, geometry=geometry, properties=copy.deepcopy(properties))
        self.id: str = extra.get("id")
        self.setVersion()
        self.setClass()

    @classmethod
    def new(cls, f):
        # a = inspect.getargspec(cls.__init__)
        a = inspect.signature(cls.__init__)
        # Does cls have an id parameter?
        # Does f have an id to carry over?
        # Let's try really hard to find an id
        i = None
        if callable(getattr(f, "getId", None)):  # if f is a FeatureWithProps
            i = f.getId()
        elif hasattr(f, "id"):
            i = f.id
        elif "id" in f:
            i = f["id"]
        elif "properties" in f and "id" in f["properties"]:  # if f is a Feature
            i = f["properties"]["id"]
        elif hasattr(f, "properties") and type(f.properties) == dict:
            i = f.properties.get("id")
        # print(f"FeatureWithProps::new: id={i}")  #, cls={cls}")
        if type(f) == dict:
            if hasattr(a, "id"):
                return cls(id=i, geometry=f["geometry"], properties=f["properties"])
            else:
                t = cls(geometry=f["geometry"], properties=f["properties"])
                if i is not None:
                    t.id = i
                return t
        else:
            if hasattr(a, "id"):
                return cls(id=i, geometry=f.geometry, properties=f.properties)
            else:
                t = cls(geometry=f.geometry, properties=f.properties)
                if i is not None:
                    t.id = i
                return t

    @staticmethod
    def convert(f):
        return EmitpyFeature.new(f)

    @staticmethod
    def betterFeatures(arr):
        return [EmitpyFeature.new(f) for f in arr]

    def version(self):
        return self.getProp(FEATPROP.VERSION)

    # def geometry(self):
    #     return self["geometry"] if "geometry" in self else None

    def coords(self):
        return self.geometry.get("coordinates")

    def props(self):
        return self.properties

    def lat(self):
        return self.geometry.coordinates[1]

    def lon(self):
        return self.geometry.coordinates[0]

    def alt(self):
        # Altitude can be stored at two places
        # Assumes Feature is <Point>
        return self.altitude()

    def geomtype(self):
        return self.geometry.type

    def is_type(self, geomtype: str):
        return geomtype == self.geomtype()

    def copy(self):
        return EmitpyFeature.new(self)  # copy.deepcopy(self)

    def setVersion(self, v: str = emitpy.__version__):
        self.setProp(FEATPROP.VERSION, v)

    def setClass(self, c: str = "", force: bool = False):
        if force or self.getClass() is None:
            self.setProp(FEATPROP.CLASS, c if c == "" else type(self).__name__)

    def getClass(self):
        return self.getProp(FEATPROP.CLASS)

    def getProp(self, name: str | FEATPROP, dflt=None):
        # Wrapper around Feature properties (inexistant in GeoJSON Feature)
        if isinstance(name, FEATPROP):
            name = name.value
        if name == FEATPROP.ALTITUDE.value:
            return self.altitude()
        return self.properties.get(name, dflt)

    def setProp(self, name: str | FEATPROP, value):
        # Wrapper around Feature properties (inexistant in GeoJSON Feature)
        if isinstance(name, FEATPROP):
            name = name.value
        if name == FEATPROP.ALTITUDE.value:
            self.setAltitude(value)
        else:
            self.properties[name] = value

    def unsetProp(self, name: str | FEATPROP):
        if isinstance(name, FEATPROP):
            name = name.value
        if name in self.properties:
            del self.properties[name]

    def getName(self):
        return self.getProp(FEATPROP.NAME)

    def setName(self, name: str):
        self.setProp(FEATPROP.NAME, name)

    def getId(self):
        return self.id if hasattr(self, "id") else self.getProp("id")

    def __hash__(self):
        return hash(self.getId())

    def get_id(self):
        return self.getId()

    def getKey(self):
        # return type(self).__name__ + ID_SEP + self.getId()
        return self.getId()

    def setId(self, ident: str):
        self.id = ident

    def addProps(self, values: dict):
        for name, value in values.items():
            self.setProp(name, value)

    def getMark(self):
        return self.getProp(FEATPROP.MARK)

    def setMark(self, mark, index: int = -1):
        self.setProp(FEATPROP.MARK, mark)
        if index >= 0:
            self.setProp(FEATPROP.MARK_SEQUENCE, index)

        # For historical reasons, tags are kept in |-separated strings like tag1|tag2, this comes from X-Plane...

    def setTag(self, tagname: str, tagvalue: str):
        tags = self.getTags(tagname)
        if tagvalue not in tags:
            tags.append(tagvalue)
        self.setTags(tagname, tags)

    def unsetTag(self, tagname: str, tagvalue: str):
        tags = self.getTags(tagname)
        ndx = -1
        try:
            ndx = tags.index(tagvalue)
        except:
            ndx = -1
        if ndx != -1:
            del tags[ndx]
        self.setTags(tagname, tags)

    def hasTag(self, tagname: str, tagvalue: str):
        tags = self.getTags(tagname)
        return tagvalue in tags

    def getTags(self, tagname: str, sep=TAG_SEP):
        # If tagname does not exist, returns empty array, not None
        tags = self.getProp(tagname)
        return tags.split(sep) if tags is not None else []

    def setTags(self, tagname: str, tags, sep=TAG_SEP):
        self.setProp(tagname, sep.join(tags))

    def hasColor(self):
        return self.getProp("marker-color") is not None or self.getProp("stroke") is not None

    def setColor(self, color: str):
        # geojson.io specific
        self.addProps({"marker-color": color, "marker-size": "medium", "marker-symbol": ""})

    def setStrokeColor(self, color: str):
        # geojson.io specific
        self.addProps({"stroke": color, "stroke-width": 2, "stroke-opacity": 1})

    def setFillColor(self, color: str):
        # geojson.io specific
        self.addProps({"fill": color, "fill-opacity": 0.5})

    def setAltitude(self, alt: float, ref: str = "ASL"):  # ref={ASL|AGL|BARO}
        # ref could be ASL, AGL, BARO
        # Altitude should be in meters
        if len(self.geometry.coordinates) > 2:
            l = list(self.geometry.coordinates)
            l[2] = alt
            self.geometry.coordinates = tuple(l)
        else:
            l = list(self.geometry.coordinates)
            l.append(alt)
            self.geometry.coordinates = tuple(l)
        self.properties[FEATPROP.ALTITUDE.value] = alt
        self.properties[FEATPROP.ALTITUDE.value + "-reference"] = ref

    def altitude(self, default: float | None = None) -> float | None:
        # Altitude can be stored at two places
        # Assumes Feature is <Point>
        if len(self.geometry.coordinates) > 2:
            return self.geometry.coordinates[2]
        alt = self.properties.get(FEATPROP.ALTITUDE.value, None)
        if alt is not None:  # write it to coordinates
            alt = float(alt)
            if len(self.geometry.coordinates) > 2:
                l = list(self.geometry.coordinates)
                l[2] = alt
                self.geometry.coordinates = tuple(l)
            else:
                l = list(self.geometry.coordinates)
                l.append(alt)
                self.geometry.coordinates = tuple(l)
            return alt
        return default

    def setSpeed(self, speed: float):
        # Speed should be in meters per second
        self.setProp(name=FEATPROP.SPEED.value, value=speed)

    def speed(self, default: float | None = None) -> float | None:
        a = self.getProp(FEATPROP.SPEED)
        if a is None or a == "None":
            return default
        return float(a)

    def setGroundSpeed(self, speed: float):
        # Speed should be in meters per second
        self.setProp(name=FEATPROP.SPEED.value, value=speed)

    def groundSpeed(self, default: float | None = None) -> float | None:
        a = self.getProp(FEATPROP.SPEED)
        if a is None or a == "None":
            return default
        return float(a)

    def setVSpeed(self, vspeed: float):
        # Vertical speed should be in meters per second
        self.setProp(FEATPROP.VERTICAL_SPEED, vspeed)

    def vspeed(self, default: float | None = None) -> float | None:
        a = self.getProp(FEATPROP.VERTICAL_SPEED)
        if a is None or a == "None":
            return default
        return float(a)

    def setCourse(self, course: float):
        # Course should be in decimal degrees, if possible confined to [0, 360[. (@todo)
        self.setProp(FEATPROP.COURSE, course)

    def course(self, default: float | None = None) -> float | None:
        a = self.getProp(FEATPROP.COURSE)
        if a is None or a == "None":
            return default
        return float(a)

    def setHeading(self, heading: float):
        # Heading should be in decimal degrees, if possible confined to [0, 360[. (@todo)
        self.setProp(FEATPROP.HEADING, heading)

    def heading(self, default: float | None = None) -> float | None:
        a = self.getProp(FEATPROP.HEADING)
        if a is None or a == "None":
            return default
        return float(a)

    def setTime(self, time: float):
        self.setProp(FEATPROP.TIME, time)

    def time(self, default: float | None = None) -> float | None:
        a = self.getProp(FEATPROP.TIME)
        if a is None or a == "None":
            return default
        return float(a)

    def setPause(self, time: float):
        self.setProp(FEATPROP.PAUSE, time)

    def addToPause(self, time: float):
        self.setProp(FEATPROP.PAUSE, self.pause(default=0) + time)  # type: ignore [operator]

    def pause(self, default: float | None = None) -> float | None:
        a = self.getProp(FEATPROP.PAUSE)
        if a is None or a == "None":
            return default
        return float(a)

    def get_timestamp(self):
        # Added for Opera
        return self.getProp(FEATPROP.EMIT_ABS_TIME, 0.0)

    def setComment(self, comment: str):
        self.setProp(FEATPROP.COMMENT, comment)

    def comment(self, default: str | None = None) -> str | None:
        a = self.getProp(FEATPROP.COMMENT)
        if a is None or a == "None":
            return default
        return a

    def getPropPath(self, path: str):
        r = JSONPath(path).parse(self.properties)
        if len(r) == 1:
            return r[0]
        if len(r) > 1:
            print(f"FeatureWithProps.getPropPath(): ambiguous return value for {path}, returning first element in list")
            return r[0]
        return None

    def getFeaturePath(self, path: str):
        r = JSONPath(path).parse(self)
        if len(r) == 1:
            return r[0]
        if len(r) > 1:
            print(f"FeatureWithProps.getFeaturePath(): ambiguous return value for {path}, returning first element in list")
            return r[0]
        return None

    def flyOver(self):
        return False


#
#
#
#
# Measures
def distance(p1, p2, units: str = "km"):
    if units == "km":
        units = "kilometers"
    if units == "m":
        units = "meters"
    return turf_distance(p1, p2, {"units": units})


def point_to_line_distance(point, line):
    return turf_point_to_line_distance(point, line)


def bearing(p1, p2):
    return turf_bearing(p1, p2)


def bbox(p1, p2):
    return turf_bbox(p1, p2)


# Move
def destination(start, length, course, units: str = "km"):
    def mkBearing(b):
        if b > 180:
            return mkBearing(b - 360)
        if b < -180:
            return mkBearing(b + 360)
        return b

    if units == "km":
        units = "kilometers"
    if units == "m":
        units = "meters"
    return asFeature(turf_destination(start, length, mkBearing(course), {"units": units}))


# Checks
def point_in_polygon(point, polygon):
    return turf_boolean_point_in_polygon(point, polygon)


def line_intersect_polygon(line, polygon) -> FeatureCollection:
    # Returns intersecting points
    return turf_line_intersect(line, polygon)


def line_intersect_polygon_count(line, polygon) -> int:
    # Returns number of intersecting points
    res = line_intersect_polygon(line, polygon)
    if res is not None:
        fc = res.get("features")
        if fc is not None:
            return len(fc)  # number of intersecting points
    return 0


# Miscellaneous
def asFeature(f):
    # some functions return dict or str
    if isinstance(f, Feature):
        return f
    return Feature(geometry=f["geometry"], properties=f["properties"])


def saveGeoJSON(filename, geojson):
    with open(filename, "w") as fp:
        json.dump(geojson.to_geojson(), fp, indent=4)


def loadGeoJSON(filename):
    data = None
    with open(filename, "r") as fp:
        data = json.load(fp)
    if data is not None:
        return FeatureCollection(features=[asFeature(f) for f in data["features"]])
    return None
