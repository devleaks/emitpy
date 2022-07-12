"""
ManagedAirport loaded from OpenStreetMap files
"""
import os.path
import json
import yaml
import logging

from geojson import Point, Feature
from turfpy.measurement import distance, bearing

from .airport import AirportBase
from emitpy.parameters import DATA_DIR
from emitpy.graph import Vertex, Edge
from emitpy.geo import Runway, Ramp

SYSTEM_DIRECTORY = os.path.join(DATA_DIR, "managedairport")

logger = logging.getLogger("OSMAirport")


# ################################
# OSM AIRPORT
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
        self.ramps_geo = None
        self.service_roads_geo = None
        self.service_roads_net = None
        self.data = None
        self.loaded = False

    def loadFromFile(self):
        self.airport_base = os.path.join(SYSTEM_DIRECTORY, self.icao)
        return [True, "do nothing"]

    def loadJSONOrYAMLFromFile(self, name):
        fname = os.path.join(self.airport_base, "osm", name)

        if os.path.exists(fname):
            with open(fname, "r") as fptr:
                if name[-5:] == ".yaml":
                    self.data = yaml.safe_load(fptr)
                else:  # JSON or GeoJSON
                    self.data = json.load(fptr)
        else:
            logger.warning(f":file: {fname} not found")
            return [False, "OSMAirport::loadJSONOrYAMLFromFile file %s not found", fname]

        return [True, f"OSMAirport::file {name} loaded"]

    def loadRunways(self):
        self.loadJSONOrYAMLFromFile("overpass-runway.json")
        if self.data is None:
            return [False, f"OSMAirport::loadRunways: could not load {fn1}"]

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

        logger.info(f":loadRunways: added {len(self.runways)} runways: {self.runways.keys()}.")
        return [True, "OSMAirport::loadRunways loaded"]


    def loadRamps(self):
        self.loadJSONOrYAMLFromFile("overpass-parking_position.json")
        if self.data is None:
            return [False, f"OSMAirport::loadRamps: could not load {fn1}"]

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
                    self.ramps[name] = Ramp(name=name,
                                               ramptype="unknown",
                                               position=center,
                                               orientation=heading,
                                               use="pax|cargo")
        self.data = None

        logger.info(f":loadRamps: added {len(self.ramps)} parkings: {sorted(self.ramps.keys())}")
        return [True, "OSMAirport::loadRamps loaded"]


    def loadOSM(self, filename, graph):
        self.loadJSONOrYAMLFromFile(filename)
        if self.data is None:
            return [False, f"OSMAirport::loadOSM: could not load {fn1}"]

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
            return status

        logger.debug(":loadPOIS: loaded")
        return [True, "GeoJSONAirport::loadPOIS loaded"]


    def loadServiceDestinations(self):
        self.loadJSONOrYAMLFromFile("servicepois.geojson")

        if self.data is not None:  # parse runways
            self.service_stops_geo = self.data
            self.data = None
            logger.info(":loadServiceDestinations: added %d features.", len(self.service_stops_geo["features"]))


        logger.debug(":loadServiceDestinations: added %d service destinations", len(self.service_destinations.keys()))
        return [True, "OSMAirport::loadServiceDestination loaded"]
