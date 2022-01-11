"""
GeoJSON Features with special meaning or type (class).
"""
from geojson import GeoJSON, Polygon, Point, Feature
from turfpy.measurement import bearing

from ..business.identity import Identity


class IdentifiedFeature(Feature, Identity):  # Alt: FeatureWithId?
    """
    A IdentifiedFeature is a Feature with mandatory identification data.
    """
    def __init__(self, geometry: GeoJSON, properties: dict, orgId: str, classId: str, typeId: str, name: str):
        Feature.__init__(self, geometry=geometry, properties=properties)
        Identity.__init__(self, orgId=orgId, classId=classId, typeId=typeId, name=name)


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
# AIRSPACE RESTRICTION (RESTRICTED AREA)
#
#
class RestrictedAirspace(Feature):

    def __init__(self, polygon: Polygon, altmin: float, altmax: float):
        Feature.__init__(self, geometry=polygon, properties={
            "type": "airspace",
            "sub-type": "restricted",
            "altmin": altmin,           # must specify ABG, ASL...
            "altmax": altmax})


# ################################@
# RAMP
#
#
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

