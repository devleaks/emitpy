# Wrapper around mig python missing geo library
# No library is satisfying...
# Inconsistencies, missing functions, errors, wrong GeoJSON handling...
#
import copy
import inspect
from jsonpath import JSONPath

from geojson import FeatureCollection, Point, LineString, Polygon
from geojson import Feature as _Feature

from turfpy.measurement import distance as turf_distance
from turfpy.measurement import destination as turf_destination
from turfpy.measurement import bearing as turf_bearing
from turfpy.measurement import bbox as turf_bbox
from turfpy.measurement import boolean_point_in_polygon as turf_boolean_point_in_polygon
from turfpy.measurement import point_to_line_distance as turf_point_to_line_distance
from turfpy.misc import line_intersect as turf_line_intersect

import emitpy
from emitpy.constants import FEATPROP, TAG_SEP


class Feature(_Feature):

    def __init__(self, geometry, properties: dict = {}, **extra):
        self["type"] = "Feature"  # see https://github.com/jazzband/geojson/issues/178
        _Feature.__init__(self, geometry=geometry, properties=properties)
        self.id = extra.get("id")


class EmitpyFeature(Feature):
    """
    A FeatureWithProps is a GeoJSON Feature<Point> with facilities to set a few standard
    properties like altitude, speed, vertical speed and properties.
    It can also set colors for geojson.io map display.
    Altitude is stored in third geometry coordinates array value:

    An OPTIONAL third-position element SHALL be the height in meters above or below the WGS 84 reference ellipsoid.
    (https://datatracker.ietf.org/doc/rfc7946/?include_text=1)
    """
    def __init__(self, id=None, geometry=None, properties=None, **extra):
        # MUST CALL BEFORE: def __init__(self, geometry: Geometry, properties: dict):
        Feature.__init__(self, id=id, geometry=geometry, properties=copy.deepcopy(properties) if properties is not None else None)
        self.setVersion()
        self.setClass()

    @classmethod
    def new(cls, f):
        # a = inspect.getargspec(cls.__init__)
        a = inspect.signature(cls.__init__)
        # Does cls have an id parameter?
        # Does f have an id to carry over?
        i = None
        if callable(getattr(f, "getId", None)):  # if f is a FeatureWithProps
            i = f.getId()
        elif hasattr(f, "id"):
            i = f.id
        elif "id" in f:
            i = f["id"]
        elif "properties" in f and "id" in f["properties"]:  # if f is a Feature
            i = f["properties"]["id"]
        # print(f"FeatureWithProps::new: id={i}")  #, cls={cls}")

        if hasattr(a, "id"):
            return cls(id=i, geometry=f["geometry"], properties=f["properties"])
        else:
            t = cls(geometry=f["geometry"], properties=f["properties"])
            if i is not None:
                t.id = i
            return t


    @staticmethod
    def convert(f):
        return EmitpyFeature.new(f)

    @staticmethod
    def betterFeatures(arr):
        return [ EmitpyFeature.convert(f) for f in arr ]

    def version(self):
        return self.getProp(FEATPROP.VERSION.value)

    def getGeometry(self):
        return self["geometry"] if "geometry" in self else None

    def geometry(self):
        return self["geometry"] if "geometry" in self else None

    def coords(self):
        return self["geometry"]["coordinates"] if (("geometry" in self) and ("coordinates" in self["geometry"])) else None

    def props(self):
        return self["properties"] if "properties" in self else None

    def lat(self):
        return self["geometry"]["coordinates"][1] if (("geometry" in self) and ("coordinates" in self["geometry"])) else None

    def lon(self):
        return self["geometry"]["coordinates"][0] if (("geometry" in self) and ("coordinates" in self["geometry"])) else None

    def geomtype(self):
        return self["geometry"]["type"] if (("geometry" in self) and ("type" in self["geometry"])) else None

    def is_type(self, geomtype: str):
        return geomtype == self.geomtype()

    def copy(self):
        return copy.deepcopy(self)

    def setVersion(self, v: str = emitpy.__version__):
        self.setProp(FEATPROP.VERSION.value, v)

    def setClass(self, c: str = None, force: bool = False):
        if force or self.getClass() is None:
            self.setProp(FEATPROP.CLASS.value, c if c is not None else type(self).__name__)

    def getClass(self):
        return self.getProp(FEATPROP.CLASS.value)

    def getProp(self, name: str):
        # Wrapper around Feature properties (inexistant in GeoJSON Feature)
        if name == FEATPROP.ALTITUDE.value:
            return self.altitude()
        if type(self["properties"]) in [dict]:
            return self["properties"].get(name)
        print("feature has no properties?")
        return None

    def setProp(self, name: str, value):
        # Wrapper around Feature properties (inexistant in GeoJSON Feature)
        if name == FEATPROP.ALTITUDE.value:
            self.setAltitude(value)
        else:
            self["properties"][name] = value

    def getName(self):
        return self.getProp(FEATPROP.NAME.value)

    def setName(self, name: str):
        self.setProp(FEATPROP.NAME.value, name)

    def getId(self):
        return self.id if hasattr(self, "id") else self.getProp("id")

    def getKey(self):
        # return type(self).__name__ + ID_SEP + self.getId()
        return self.getId()

    def setId(self, ident: str):
        self.id = ident

    def addProps(self, values: dict):
        for name, value in values.items():
            self.setProp(name, value)

    def getMark(self):
        return self.getProp(FEATPROP.MARK.value)

    def setMark(self, mark):
        return self.setProp(FEATPROP.MARK.value, mark)

        # For historical reasons, tags are kept in |-separated strings like tag1|tag2.
    def setTag(self, tagname: str, tagvalue: str):
        tags = self.getTags(tagname)
        if tagvalue not in tags:
            tags.append(tagvalue)
        self.setTags(tagname, tags)

    def unsetTag(self, tagname:str, tagvalue: str):
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
        self.addProps({
            "marker-color": color,
            "marker-size": "medium",
            "marker-symbol": ""
        })

    def setStrokeColor(self, color: str):
        # geojson.io specific
        self.addProps({
            "stroke": color,
            "stroke-width": 2,
            "stroke-opacity": 1
        })

    def setFillColor(self, color: str):
        # geojson.io specific
        self.addProps({
            "fill": color,
            "fill-opacity": 0.5
        })

    def setAltitude(self, alt: float, ref: str = "ASL"):  # ref={ASL|AGL|BARO}
        # ref could be ASL, AGL, BARO
        # Altitude should be in meters
        if len(self["geometry"]["coordinates"]) > 2:
            self["geometry"]["coordinates"][2] = alt
        else:
            self["geometry"]["coordinates"].append(alt)
        self["properties"][FEATPROP.ALTITUDE.value] = alt
        self["properties"][FEATPROP.ALTITUDE.value + "-reference"] = ref

    def altitude(self, default: float = None):
        # Altitude can be stored at two places
        # Assumes Feature is <Point>
        if len(self["geometry"]["coordinates"]) > 2:
            return self["geometry"]["coordinates"][2]
        alt = self["properties"][FEATPROP.ALTITUDE.value] if FEATPROP.ALTITUDE.value in self["properties"] else None
        if alt is not None:  # write it to coordinates
            alt = float(alt)
            if len(self["geometry"]["coordinates"]) > 2:
                self["geometry"]["coordinates"][2] = alt
            else:
                self["geometry"]["coordinates"].append(alt)
            return alt
        return default

    def alt(self):
        return self.altitude()

    def setSpeed(self, speed: float):
        # Speed should be in meters per second
        self.setProp(name=FEATPROP.SPEED.value, value=speed)

    def speed(self, default: float = None):
        a = self.getProp(FEATPROP.SPEED.value)
        if a is None or a == "None":
            return default
        return float(a)


    def setGroundSpeed(self, speed: float):
        # Speed should be in meters per second
        self.setProp(name=FEATPROP.SPEED.value, value=speed)

    def groundSpeed(self, default: float = None):
        a = self.getProp(FEATPROP.SPEED.value)
        if a is None or a == "None":
            return default
        return float(a)


    def setVSpeed(self, vspeed: float):
        # Vertical speed should be in meters per second
        self.setProp(FEATPROP.VERTICAL_SPEED.value, vspeed)

    def vspeed(self, default: float = None):
        a = self.getProp(FEATPROP.VERTICAL_SPEED.value)
        if a is None or a == "None":
            return default
        return float(a)


    def setCourse(self, course: float):
        # Course should be in decimal degrees, if possible confined to [0, 360[. (@todo)
        self.setProp(FEATPROP.COURSE.value, course)

    def course(self, default: float = None):
        a = self.getProp(FEATPROP.COURSE.value)
        if a is None or a == "None":
            return default
        return float(a)


    def setHeading(self, heading: float):
        # Heading should be in decimal degrees, if possible confined to [0, 360[. (@todo)
        self.setProp(FEATPROP.HEADING.value, heading)

    def heading(self, default: float = None):
        a = self.getProp(FEATPROP.HEADING.value)
        if a is None or a == "None":
            return default
        return float(a)


    def setTime(self, time: float):
        self.setProp(FEATPROP.TIME.value, time)

    def time(self, default: float = None):
        a = self.getProp(FEATPROP.TIME.value)
        if a is None or a == "None":
            return default
        return float(a)


    def setPause(self, time: float):
        self.setProp(FEATPROP.PAUSE.value, time)

    def addToPause(self, time: float):
        self.setProp(FEATPROP.PAUSE.value, self.pause(0) + time)

    def pause(self, default: float = None):
        a = self.getProp(FEATPROP.PAUSE.value)
        if a is None or a == "None":
            return default
        return float(a)


    def setComment(self, comment: str):
        self.setProp(FEATPROP.COMMENT.value, comment)

    def comment(self, default: str = None):
        a = self.getProp(FEATPROP.COMMENT.value)
        if a is None or a == "None":
            return default
        return a


    def getPropPath(self, path: str):
        r = JSONPath(path).parse(self["properties"])
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
