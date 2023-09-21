"""
GeoJSON Features with special meaning or type (class).
"""
from datetime import datetime, timedelta

from emitpy.constants import FEATPROP, POI_TYPE, SERVICE_COLOR
from emitpy.geo.turf import Polygon, Point, LineString, Feature
from emitpy.geo.turf import EmitpyFeature as FeatureWithProps
from emitpy.geo.turf import bearing, destination


# ################################
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


# ################################
# RAMP
#
#
class Ramp(FeatureWithProps):

    def __init__(self, name: str, ramptype: str, position: [float], orientation: float, use: str):

        FeatureWithProps.__init__(self, geometry=Point(position), properties={
            "name": name,
            "type": "ramp",
            "sub-type": ramptype,  # should be limited to {gate|tie-down}, either gate or else.
            "use": use,
            "orientation": orientation,
            "available": None})

        self.service_pois = {}
        self.ac_nose = None

    def getInfo(self):
        a = self.getName()[0]
        if a == "5":  # Special OTHH
            a = "J"

        return {
            "name": self.getName(),
            "apron": a.upper()
        }

    def getId(self):
        # remove spaces
        return "".join(self.getName().split())

    def getResourceId(self):
        return self.getName()

    def hasJetway(self) -> bool:
        # by opposition, if no jetway, assume remote parking area
        test = self.getProp(FEATPROP.JETWAY.value)  # must be exactly True
        return test if test == True else False

    def busy(self):
        self["properties"]["available"] = False

    def available(self):
        self["properties"]["available"] = True

    def isAvailable(self):
        if "available" in self["properties"]:
            return self["properties"]["available"]
        return None

    def getServicePOI(self, service, aircraft):
        if aircraft.iata in self.service_pois:
            service_pois = self.service_pois[aircraft.iata]
            return service_pois[service] if service in service_pois else None
        return None

    def getServicePOIs(self, service, aircraft):
        """
        Returns all service positions for supplied service name.
        Example for service fuel, returns [fuel, fuel2, fuel3...] if they exist.
        Number suffix starts with 2 up to 9.
        Returns array of service POIs.

        :param      service:   The service
        :type       service:   { type_description }
        :param      aircraft:  The aircraft
        :type       aircraft:  { type_description }
        """
        if aircraft.iata in self.service_pois:
            service_pois = self.service_pois[aircraft.iata]
            if service in service_pois:
                pos = [service_pois[service]]
                c = 2
                s = f"{service}{c}"
                while s in service_pois and c < 10:
                    pos.append(service_pois[s])
                    c = c + 1
                    s = f"{service}{c}"
            return pos
        return None

    def makeServicePOIs(self, aircraft: "AircraftType", redis=None):
        def sign(x):
            return -1 if x < 0 else (0 if x == 0 else 1)

        if aircraft.iata in self.service_pois:
            if len(self.service_pois[aircraft.iata]) > 0:
                return (True, "Ramp::makeServicePOIs: already created")
            else:
                return (False, f"Ramp::makeServicePOIs: no POI for {aircraft.iata}")

        aircraft_length = aircraft.get("length")
        if aircraft_length is None:
            aircraft_length = 50  # m

        aircraft_width = aircraft.get("wingspan")
        if aircraft_width is None:
            aircraft_width = 45  # m

        service_pois = {}

        # Parking position (center)n.
        self.setColor("#dddd00")
        heading = self.getProp(FEATPROP.ORIENTATION.value)
        antiheading = heading - 180
        if antiheading < 0:
            antiheading = antiheading + 360
        service_pois["center"] = self

        # compute parking begin (nose tip of plane)
        parking_nose = destination(self, aircraft_length / 2000, heading)
        parking_nose = FeatureWithProps.new(parking_nose)
        parking_nose.setColor("#dd0000")
        service_pois["nose"] = parking_nose

        # compute parking end
        parking_end = destination(self, aircraft_length / 1000, antiheading)
        parking_end = FeatureWithProps.new(parking_end)
        parking_end.setColor("#dd0000")
        service_pois["end"] = parking_end

        # for each service
        # 1=dist along axis, 2=dist away from axis, left or right, 3=heading of vehicle,
        # optional 4=height to match ac reference point.
        gseprofile = aircraft.getGSEProfile(redis=redis)
        positions = gseprofile["services"]
        for svc in positions:
            poiaxe = destination(self,   positions[svc][0]/1000, antiheading)
            poilat = destination(poiaxe, positions[svc][1]/1000, antiheading + 90)
            pos = FeatureWithProps.new(poilat)
            pos.setProp(FEATPROP.POI_TYPE.value, POI_TYPE.RAMP_SERVICE_POINT.value)
            pos.setProp(FEATPROP.SERVICE.value, svc)
            # May be POI is not a service, but a rest position,
            # or another position like fuel2, baggage6, etc.
            values = tuple(item.value for item in SERVICE_COLOR)
            c = SERVICE_COLOR[svc.upper()].value if svc.upper() in values else "#aaaaaa"
            pos.setColor(c)
            pos.setProp("vehicle-heading", positions[svc][2])
            if len(positions[svc]) > 3:
                pos.setProp("vehicle-height", positions[svc][3])
            service_pois[svc] = pos

        self.service_pois[aircraft.iata] = service_pois
        # printFeatures(list(self.service_pois[aircraft.iata].values()), f"ramp position for {aircraft.iata}")
        return (True, "Ramp::makeServicePOIs: created")


# ################################
# RUNWAY
#
#
class Runway(FeatureWithProps):

    def __init__(self, name: str, width: float, lat1: float, lon1: float, lat2: float, lon2: float, surface: Polygon):
        p1 = Feature(geometry=Point((lon1, lat1)))
        p2 = Feature(geometry=Point((lon2, lat2)))
        brng = bearing(p1, p2)
        self.end = None   # opposite runway
        self.uuid = name  # not correct, but acceptable default value, set unique for both "sides" of runway
                          # some rare runways are one way only... (EDDF)
        FeatureWithProps.__init__(self, geometry=surface, properties={
            "type": "runway",
            "name": name,
            "width": width,
            "orientation": brng,
            "line": LineString([(lon1,lat1), (lon2,lat2)])
        })

    def getInfo(self):
        return {
            "name": self.getName(),
            "resource": self.getResourceId()
        }

    def getId(self):
        return self.getName()


    def getResourceId(self):
        """
        Resource name must be the same for either direction
        """
        return self.uuid


# ################################
# SERVICE PARKING
#
#
class ServiceParking(FeatureWithProps):
    """
    A service parking is a depot or a destination in X-Plane
    for equipment movements (row codes 1400, 1401).
    """
    def __init__(self, name: str, parking_type: str, position: [float], orientation: float, use: str):
        FeatureWithProps.__init__(self, geometry=Point(position), properties={
            "type": "service-parking",
            "sub-type": parking_type,
            "parking-use": use,
            "orientation": orientation})


# ################################
# POINT WITH WEATHER
#
#
class WeatherPoint(FeatureWithProps):
    """
    A feature with Weather attached to it and weather-validity information.
    """
    TROPOSPHERE = 20000 # m
    def __init__(self, position: [float], weather):
        FeatureWithProps.__init__(self, geometry=Point(position), properties={
            "weather": weather})

        self.dt_start = datetime(1970, 1, 1, 0, 0)
        self.dt_end = datetime.now() + timedelta(years=100)  # won't be here to blame if it fails.
        self.bbox = [90, 180, -90, -180]
        self.alt_min = 0   # MSL
        self.alt_max = WeatherPoint.TOPOSPHERE

        self.sunset = None   # UTC for location
        self.sunrise = None 


    def valid_date(self, moment: datetime):
        return moment >= self.df_start and moment <= self.dt_end

    def valid_alt(self, alt):
        return alt >= self.alt_min and moment <= self.alt_max
        
    def valid_pos(self, pos):
        return self.bbox[0] > pos[0] and self.bbox[2] > pos[0] and self.bbox[1] > pos[1] and self.bbox[3] > pos[1]
        
    def get_wind(self):
        # returns (speed (m/s), direction (° True, None if variable))
        # Used to determine RWY in use (QFU), used to determine wind at altitude
        return (0, None)

    def get_precip(self):
        # returns (cm of precipitation for last hour, type of precipitation, default to WATER0)
        # Used to determine takeoff and landing distance
        return (0, None)

