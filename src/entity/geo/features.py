"""
GeoJSON Features with special meaning or type (class).
"""
import copy
from geojson import Polygon, Point, Feature
from geojson.geometry import Geometry
from turfpy.measurement import bearing, destination

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
    Altitude is stored in third geometry coordinates array value.
    """
    def __init__(self, geometry: Geometry, properties: dict):
        Feature.__init__(self, geometry=geometry, properties=copy.deepcopy(properties))

    def getProp(self, name: str):
        # Wrapper around Feature properties (inexistant in GeoJSON Feature)
        return self["properties"][name] if name in self["properties"] else "None"

    def setProp(self, name: str, value):
        # Wrapper around Feature properties (inexistant in GeoJSON Feature)
        self["properties"][name] = value

    def addProps(self, values: dict):
        for name, value in values.items():
            self.setProp(name, value)

        # geojson.io specific
    def setColor(self, color: str):
        self.addProps({
            "marker-color": color,
            "marker-size": "medium",
            "marker-symbol": ""
        })

    def setStrokeColor(self, color: str):
        self.addProps({
            "stroke": color,
            "stroke-width": 2,
            "stroke-opacity": 1
        })

    def setFillColor(self, color: str):
        self.addProps({
            "fill": color,
            "fill-opacity": 0.5
        })

    def setAltitude(self, alt):
        if len(self["geometry"]["coordinates"]) > 2:
            self["geometry"]["coordinates"][2] = alt
        else:
            self["geometry"]["coordinates"].append(alt)
        self.setProp("altitude", alt)

    def altitude(self):
        return self["geometry"]["coordinates"][2] if len(self["geometry"]["coordinates"]) > 2 else None

    def setSpeed(self, speed):
        self.setProp(name="speed", value=speed)

    def speed(self):
        return self.getProp("speed")

    def setVSpeed(self, vspeed):
        self.setProp("vspeed", vspeed)

    def vspeed(self):
        return self.getProp("vspeed")

    def setTime(self, time):
        self.setProp("time", time)

    def time(self):
        return self.getProp("time")


# ################################@
# LOCATION
#
#
class Location(Feature):  # Location(Feature)
    """
    A Location is a named Feature<Point> in a city in a country.
    """
    def __init__(self, name: str, city: str, country: str, lat: float, lon: float, alt: float):

        Feature.__init__(self, geometry=Point((lon, lat, alt)), properties={
            "country": country,
            "city": city,
            "name": name
        })


# ################################@
# RAMP
#
#
class Ramp(FeatureWithProps):

    def __init__(self, name: str, ramptype: str, position: [float], orientation: float, use: str):

        Feature.__init__(self, geometry=Point(position), properties={
            "name": name,
            "type": "ramp",
            "sub-type": ramptype,
            "use": use,
            "orientation": orientation,
            "available": None})

        self.service_pois = {}

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

    def makeServicePOIs(self, data):
        def sign(x):
            return -1 if x < 0 else (0 if x == 0 else 1)

        OFFSET = 30
        heading = self.getProp("orientation")
        # compute offset
        origin = destination(self, OFFSET / 1000, heading, {"units": "km"})
        # for each service
        positions = data["services"]
        for svc in positions:
            poiax = destination(origin, positions[svc][0]/1000, heading - 180, {"units": "km"})
            poilat = destination(poiax, positions[svc][1]/1000, heading + sign(positions[svc][1]) * 90, {"units": "km"})
            pos = FeatureWithProps(geometry=poilat["geometry"], properties=poilat["properties"])
            pos.setProp("service", svc)
            pos.setProp("heading", positions[svc][2])
            self.service_pois[svc] = pos

        return (True, "Ramp::makeServicePOIs: created")


# ################################@
# RUNWAY
#
#
class Runway(Feature):

    def __init__(self, name: str, width: float, lat1: float, lon1: float, lat2: float, lon2: float, surface: Polygon):
        p1 = Feature(geometry=Point((lon1, lat1)))
        p2 = Feature(geometry=Point((lon2, lat2)))
        brng = bearing(p1, p2)
        Feature.__init__(self, geometry=surface, properties={
            "type": "runway",
            "name": name,
            "width": width,
            "orientation": brng})


# ################################@
# SERVICE PARKING
#
#
class ServiceParking(Feature):

    def __init__(self, name: str, parking_type: str, position: [float], orientation: float, use: str):
        Feature.__init__(self, geometry=Point(position), properties={
            "type": "service-parking",
            "sub-type": parking_type,
            "parking-use": use,
            "orientation": orientation})
