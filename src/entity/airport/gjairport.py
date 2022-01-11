# Airport as defined in X-Plane
#
import os.path
import re
import logging

from geojson import Point, Polygon, Feature
from turfpy.measurement import distance, destination, bearing

from .airport import Airport
from ..graph import Vertex, Edge
from ..geo import Ramp, ServiceParking, Runway
from ..parameters import DATA_DIR

SYSTEM_DIRECTORY = os.path.join(DATA_DIR, "x-plane")

logger = logging.getLogger("GeoJSONAirport")


# ################################@
# GEOJSON AIRPORT
#
#
class GeoJSONAirport(Airport):
    """
    Airport represetation
    """
    def __init__(self, icao: str, iata: str, name: str, city: str, country: str, region: str, lat: float, lon: float, alt: float):
        Airport.__init__(self, icao=icao, iata=iata, name=name, city=city, country=country, region=region, lat=lat, lon=lon, alt=alt)
        self.scenery_pack = False
        self.atc_ground = None
        self.loaded = False

    def loadFromFile(self):
        logging.debug("GeoJSONAirport::loadFromFile: loaded")
        return [True, "GeoJSONAirport::loadFromFile: loaded"]

    def loadRunways(self):
        logging.debug("GeoJSONAirport::loadRunways: added %d runways", len(self.runways.keys()))
        return [True, "GeoJSONAirport::loadRunways loaded"]

    def loadParkings(self):
        logging.debug("GeoJSONAirport::loadParkings: added %d parkings", len(self.parkings.keys()))
        return [True, "GeoJSONAirport::loadParkings loaded"]

    def loadTaxiways(self):
        logging.info("GeoJSONAirport::loadTaxiways: added %d nodes, %d edges.", len(self.taxiways.vert_dict), len(self.taxiways.edges_arr))
        return [True, "GeoJSONAirport::loadTaxiways loaded"]

    def loadServiceRoads(self):
        logging.info("GeoJSONAirport::loadServiceRoads: added %d nodes, %d edges.", len(self.service_roads.vert_dict), len(self.service_roads.edges_arr))
        return [True, "GeoJSONAirport::loadServiceNetwork loaded"]

    def loadServiceDestinations(self):
        logging.debug("GeoJSONAirport::loadServiceDestinations: added %d service destinations", len(self.service_destinations.keys()))
        return [True, "GeoJSONAirport::loadServiceDestination loaded"]

