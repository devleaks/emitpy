# Airport as defined in X-Plane
#
import os.path
import json
import yaml
import logging

from geojson import Point, Feature
from turfpy.measurement import distance, bearing

from .airport import AirportBase
from ..parameters import DATA_DIR
from ..graph import Vertex, Edge
from ..geo import Runway, Ramp

SYSTEM_DIRECTORY = os.path.join(DATA_DIR, "managedairport")

logger = logging.getLogger("OSMAirport")


# ################################@
# GEOJSON AIRPORT
#
#
class OSMAirport(AirportBase):
    """
    Airport represetation extracted from OSM overpass queries
    """
    def __init__(self, icao: str, iata: str, name: str, city: str, country: str, region: str, lat: float, lon: float, alt: float):
        AirportBase.__init__(self, icao=icao, iata=iata, name=name, city=city, country=country, region=region, lat=lat, lon=lon, alt=alt)
        self.airport_base = None
        self.taxiways_geo = None
        self.taxiways_net = None
        self.parkings_geo = None
        self.service_roads_geo = None
        self.service_roads_net = None
        self.data = None
        self.loaded = False

    def loadFromFile(self):
        self.airport_base = os.path.join(SYSTEM_DIRECTORY, self.icao)
        return [True, "do nothing"]

    def loadFromFile2(self, name):
        fname = os.path.join(self.airport_base, "osm", name)

        if os.path.exists(fname):
            with open(fname, "r") as fptr:
                if name[-5:] == ".yaml":
                    self.data = yaml.safe_load(fptr)
                else:  # JSON or GeoJSON
                    self.data = json.load(fptr)
        else:
            logger.warning(":file: %s not found" % fname)
            return [False, "OSMAirport::loadRunways file %s not found", fname]

        return [True, "OSMAirport::file %s loaded" % name]

    def loadRunways(self):
        self.loadFromFile2("overpass-runway.json")
        if self.data is None:
            return [False, "OSMAirport::loadRunways: could not load %s" % fn1]

        points = {}
        for el in self.data["elements"]:
            if el["type"] == "node":
                points[el["id"]] = Point((el["lon"], el["lat"]))


        for el in self.data["elements"]:
            if el["type"] == "way":
                aeroway = el["tags"]["aeroway"] if ("tags" in el) and ("aeroway" in el["tags"]) else None
                if aeroway == "runway":  # OK
                    name = el["tags"]["ref"] if ("tags" in el) and ("ref" in el["tags"]) else None
                    start = points[el["nodes"][0]]
                    end = points[el["nodes"][-1]]
                    # Runway(name: str, width: float, lat1: float, lon1: float, lat2: float, lon2: float, surface: Polygon):
                    self.runways[name] = Runway(name=name, width=float(el["tags"]["width"]),
                                                lat1=start["coordinates"][1],
                                                lon1=start["coordinates"][0],
                                                lat2=end["coordinates"][1],
                                                lon2=end["coordinates"][0],
                                                surface=None)

        self.data = None

        logger.info(":loadRunways: added %d runways: %s." % (len(self.runways), self.runways.keys()))
        return [True, "OSMAirport::loadRunways loaded"]


    def loadParkings(self):
        self.loadFromFile2("overpass-parking_position.json")
        if self.data is None:
            return [False, "OSMAirport::loadParkings: could not load %s" % fn1]

        points = {}
        for el in self.data["elements"]:
            if el["type"] == "node":
                points[el["id"]] = Point((el["lon"], el["lat"]))

        for el in self.data["elements"]:
            if el["type"] == "way":
                aeroway = el["tags"]["aeroway"] if ("tags" in el) and ("aeroway" in el["tags"]) else None
                if aeroway == "parking_position":  # OK
                    name = el["tags"]["ref"] if ("tags" in el) and ("ref" in el["tags"]) else None
                    start = points[el["nodes"][0]]
                    end = points[el["nodes"][-1]]
                    heading = bearing(Feature(geometry=start), Feature(geometry=end))
                    center = start  # for now
                    # Ramp (name: str, ramptype: str, position: [float], orientation: float, use: str):
                    self.parkings[name] = Ramp(name=name,
                                               ramptype="unknown",
                                               position=center,
                                               orientation=heading,
                                               use="pax|cargo")
        self.data = None

        logger.info(":loadParkings: added %d parkings: %s" % (len(self.parkings), sorted(self.parkings.keys()) ))
        return [True, "OSMAirport::loadParkings loaded"]


    def loadOSM(self, filename, graph):
        self.loadFromFile2(filename)
        if self.data is None:
            return [False, "OSMAirport::loadOSM: could not load %s" % fn1]

        points = {}
        for el in self.data["elements"]:
            if el["type"] == "node":
                points[el["id"]] = Point((el["lon"], el["lat"]))

        for el in self.data["elements"]:
            if el["type"] == "way":
                name = el["tags"]["ref"] if ("tags" in el) and ("ref" in el["tags"]) else None
                last = None
                idx = 0
                for n in el["nodes"]:
                    v = Vertex(node=n, point=points[n], name=name)
                    graph.add_vertex(v)
                    if last is not None:
                        d = distance(last, v)
                        graph.add_edge(Edge(src=last, dst=v, weight=d, directed=False))
                    last = v
                    idx = idx + 1

        self.data = None

        logger.info(":loadOSM: added %d nodes, %d edges.", len(graph.vert_dict), len(graph.edges_arr))
        return [True, "OSMAirport::loadOSM loaded"]

    def loadTaxiways(self):
        return self.loadOSM("overpass-taxiway.json", self.taxiways)

    def loadServiceRoads(self):
        return self.loadOSM("overpass-highway.json", self.service_roads)


    def loadPOIS(self):
        status = self.loadServiceDestinations()

        if not status[0]:
            return [False, status[1]]

        logger.debug(":loadPOIS: loaded")
        return [True, "GeoJSONAirport::loadPOIS loaded"]


    def loadServiceDestinations(self):
        self.loadFromFile2("servicepois.geojson")

        if self.data is not None:  # parse runways
            self.service_stops_geo = self.data
            self.data = None
            logger.info(":loadServiceDestinations: added %d features.", len(self.service_stops_geo["features"]))


        logger.debug(":loadServiceDestinations: added %d service destinations", len(self.service_destinations.keys()))
        return [True, "OSMAirport::loadServiceDestination loaded"]
