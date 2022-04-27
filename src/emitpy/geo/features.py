"""
GeoJSON Features with special meaning or type (class).
"""
import copy
from geojson import Polygon, Point, Feature
from geojson.geometry import Geometry
from turfpy.measurement import bearing, destination
from .utils import printFeatures
from ..constants import FEATPROP, POI_TYPE, TAG_SEP, SERVICE_COLOR

# from ..business.identity import Identity


# ################################@
# IDENTIFIED FEATURE (=GEOJSON FEATURE WITH COMPLEX ID)
#
#
# class IdentifiedFeature(Feature, Identity):  # Alt: FeatureWithId?
#     """
#     A IdentifiedFeature is a Feature with mandatory identification data.
#     """
#     def __init__(self, geometry: Geometry, properties: dict, orgId: str, classId: str, typeId: str, name: str):
#         Feature.__init__(self, geometry=geometry, properties=properties)
#         Identity.__init__(self, orgId=orgId, classId=classId, typeId=typeId, name=name)


# ################################@
# FEATUREWITHPROPS
#
#
class FeatureWithProps(Feature):
    """
    A FeatureWithProps is a GeoJSON Feature<Point> with facilities to set a few standard
    properties like altitude, speed, vertical speed and properties.
    It can also set colors for geojson.io map display.
    Altitude is stored in third geometry coordinates array value:

    An OPTIONAL third-position element SHALL be the height in meters above or below the WGS 84 reference ellipsoid.
    (https://datatracker.ietf.org/doc/rfc7946/?include_text=1)
    """
    def __init__(self, id=None, geometry=None, properties=None, **extra):
        # before: def __init__(self, geometry: Geometry, properties: dict):
        self["type"] = "Feature"  # see https://github.com/jazzband/geojson/issues/178
        Feature.__init__(self, id=id, geometry=geometry, properties=copy.deepcopy(properties) if properties is not None else None)

    @classmethod
    def new(cls, f):
        return cls(geometry=f["geometry"], properties=f["properties"])

    @staticmethod
    def convert(f):
        return FeatureWithProps.new(f)

    @staticmethod
    def betterFeatures(arr):
        return [ FeatureWithProps.convert(f) for f in arr ]


    def geometry(self):
        return self["geometry"] if "geometry" in self else None

    def coords(self):
        return self["geometry"]["coordinates"] if (("geometry" in self) and ("coordinates" in self["geometry"])) else None

    def geomtype(self):
        return self["geometry"]["type"] if (("geometry" in self) and ("type" in self["geometry"])) else None

    def is_type(self, geomtype: str):
        return geomtype == self.geomtype()

    def copy(self):
        return copy.deepcopy(self)

    def getProp(self, name: str):
        # Wrapper around Feature properties (inexistant in GeoJSON Feature)
        if name == FEATPROP.ALTITUDE.value:
            return self.altitude()
        return self["properties"][name] if name in self["properties"] else None

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
        return self.id

    def setId(self, ident: str):
        self.id = ident

    def addProps(self, values: dict):
        for name, value in values.items():
            self.setProp(name, value)

        # For historical reasons, tags are kept in |-separated strings like tag1|tag2.
    def setTag(self, tagname, tagvalue):
        tags = self.getTags(tagname)
        if tagvalue not in tags:
            tags.append(tagvalue)
        self.setTags(tagname, tags)

    def unsetTag(self, tagname, tagvalue):
        tags = self.getTags(tagname)
        ndx = -1
        try:
            ndx = tags.index(tagvalue)
        except:
            ndx = -1
        if ndx != -1:
            del tags[ndx]
        self.setTags(tagname, tags)

    def hasTag(self, tagname, tagvalue):
        tags = self.getTags(tagname)
        return tagvalue in tags

    def getTags(self, tagname, sep=TAG_SEP):
        # If tagname does not exist, returns empty array, not None
        tags = self.getProp(tagname)
        return tags.split(sep) if tags is not None else []

    def setTags(self, tagname, tags, sep=TAG_SEP):
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

    def setAltitude(self, alt):
        if len(self["geometry"]["coordinates"]) > 2:
            self["geometry"]["coordinates"][2] = alt
        else:
            self["geometry"]["coordinates"].append(alt)
        self["properties"][FEATPROP.ALTITUDE.value] = alt

    def altitude(self, default=None):
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

    def setSpeed(self, speed):
        self.setProp(name=FEATPROP.SPEED.value, value=speed)

    def speed(self, default=None):
        a = self.getProp(FEATPROP.SPEED.value)
        if a is None or a == "None":
            return default
        return float(a)


    def setVSpeed(self, vspeed):
        self.setProp(FEATPROP.VERTICAL_SPEED.value, vspeed)

    def vspeed(self, default=None):
        a = self.getProp(FEATPROP.VERTICAL_SPEED.value)
        if a is None or a == "None":
            return default
        return float(a)


    def setTime(self, time):
        self.setProp(FEATPROP.TIME.value, time)

    def time(self, default=None):
        a = self.getProp(FEATPROP.TIME.value)
        if a is None or a == "None":
            return default
        return float(a)


    def setPause(self, time):
        self.setProp(FEATPROP.PAUSE.value, time)

    def pause(self, default=None):
        a = self.getProp(FEATPROP.PAUSE.value)
        if a is None or a == "None":
            return default
        return float(a)


# ################################@
# LOCATION
#
#
class Location(FeatureWithProps):  # Location(Feature)
    """
    A Location is a named Feature<Point> in a city in a country.
    """
    def __init__(self, name: str, city: str, country: str, lat: float, lon: float, alt: float):

        FeatureWithProps.__init__(self, geometry=Point((lon, lat, alt)), properties={
            FEATPROP.COUNTRY.value: country,
            FEATPROP.CITY.value: city,
            FEATPROP.NAME.value: name
        })


# ################################@
# RAMP
#
#
class Ramp(FeatureWithProps):

    def __init__(self, name: str, ramptype: str, position: [float], orientation: float, use: str):

        FeatureWithProps.__init__(self, geometry=Point(position), properties={
            "name": name,
            "type": "ramp",
            "sub-type": ramptype,
            "use": use,
            "orientation": orientation,
            "available": None})

        self.service_pois = {}

    def getInfo(self):
        a = self.getName()[0]
        if a == "5":
            a = "J"

        return {
            "name": self.getName(),
            "apron": a.upper()
        }

    def getId(self):
        # remove spaces
        return "".join(self.getName().split())

    def busy(self):
        self["properties"]["available"] = False

    def available(self):
        self["properties"]["available"] = True

    def isAvailable(self):
        if "available" in self["properties"]:
            return self["properties"]["available"]
        return None

    def getServicePOI(self, service):
        return self.service_pois[service] if service in self.service_pois else None

    def makeServicePOIs(self, aircraft):
        def sign(x):
            return -1 if x < 0 else (0 if x == 0 else 1)

        # Parking position (center) is about aircraft nose tip position.
        self.setColor("#dddd00")
        heading = self.getProp(FEATPROP.ORIENTATION.value)
        antiheading = heading - 180
        if antiheading < 0:
            antiheading = antiheading + 360

        aircraft_length = aircraft.get("length")
        if aircraft_length is None:
            aircraft_length = 50  # m

        # compute parking end
        parking_end = destination(self, aircraft_length / 1000, antiheading, {"units": "km"})
        parking_end = FeatureWithProps.new(parking_end)
        parking_end.setColor("#dd0000")
        self.service_pois["center"] = self
        self.service_pois["end"] = parking_end

        # for each service
        # 1=dist along axis, 2=dist away from axis, left or right, 3=heading of vehicle
        positions = aircraft.gseprofile["services"]
        for svc in positions:
            poiaxe = destination(self,   positions[svc][0]/1000, antiheading, {"units": "km"})
            poilat = destination(poiaxe, positions[svc][1]/1000, antiheading + 90, {"units": "km"})
            pos = FeatureWithProps.new(poilat)
            pos.setProp(FEATPROP.POI_TYPE.value, POI_TYPE.RAMP_SERVICE_POINT.value)
            pos.setProp(FEATPROP.SERVICE.value, svc)
            pos.setColor(SERVICE_COLOR[svc.upper()].value)
            pos.setProp("vehicle-heading", positions[svc][2])
            self.service_pois[svc] = pos

        # printFeatures(list(self.service_pois.values()), "ramp position")
        return (True, "Ramp::makeServicePOIs: created")


# ################################@
# RUNWAY
#
#
class Runway(FeatureWithProps):

    def __init__(self, name: str, width: float, lat1: float, lon1: float, lat2: float, lon2: float, surface: Polygon):
        p1 = Feature(geometry=Point((lon1, lat1)))
        p2 = Feature(geometry=Point((lon2, lat2)))
        brng = bearing(p1, p2)
        FeatureWithProps.__init__(self, geometry=surface, properties={
            "type": "runway",
            "name": name,
            "width": width,
            "orientation": brng})

    def getInfo(self):
        return {
            "name": self.getName()
        }

    def getId(self):
        return self.getName()


# ################################@
# SERVICE PARKING
#
#
class ServiceParking(FeatureWithProps):
    """
    A service parking is a depot or a destination in X-Plane
    for service vehicle movements (row codes 1400, 1401).
    """
    def __init__(self, name: str, parking_type: str, position: [float], orientation: float, use: str):
        FeatureWithProps.__init__(self, geometry=Point(position), properties={
            "type": "service-parking",
            "sub-type": parking_type,
            "parking-use": use,
            "orientation": orientation})
