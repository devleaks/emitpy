"""
Emit
"""
import copy
from geojson import Feature, Point


class EmitPoint(Feature):
    """
    A path point is a Feature with a Point geometry and mandatory properties for movements speed and altitude.
    THe name of the point is the synchronization name.
    """
    def __init__(self, geometry: Union[Point, LineString], properties: dict):
        Feature.__init__(self, geometry=geometry, properties=copy.deepcopy(properties))
        self._speed = None
        self._vspeed = None

    def getProp(self, propname: str):
        # Wrapper around Feature properties (inexistant in GeoJSON Feature)
        return self["properties"][propname] if propname in self["properties"] else "None"

    def setProp(self, name: str, value):
        # Wrapper around Feature properties (inexistant in GeoJSON Feature)
        self["properties"][name] = value

    def setColor(self, color: str):
        # geojson.io specific
        self["properties"]["marker-color"] = color
        self["properties"]["marker-size"] = "medium"
        self["properties"]["marker-symbol"] = ""

    def setAltitude(self, alt):
        if len(self["geometry"]["coordinates"]) > 2:
            self["geometry"]["coordinates"][2] = alt
        else:
            self["geometry"]["coordinates"].append(alt)
        self["properties"]["altitude"] = alt

    def altitude(self):
        if len(self["geometry"]["coordinates"]) > 2:
            return self["geometry"]["coordinates"][2]
        else:
            return None

    def setSpeed(self, speed):
        self._speed = speed
        self["properties"]["speed"] = speed

    def speed(self):
        return self._speed

    def setVSpeed(self, vspeed):
        self._vspeed = vspeed
        self["properties"]["vspeed"] = vspeed

    def vspeed(self):
        return self._vspeed



class Emit:
    """
    Emit takes a  FeatureCollection of decorated Feaures to produce a FeatureCollection of decorated features ready for emission.
    """

    def __init__(self, move, start, end, synch, moment):
        self.move = move
        self.broadcast = None  # [ EmitPoint ]

    def emit(self):
        self.broadcast = []
        pass
