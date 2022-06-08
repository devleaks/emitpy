"""
ManagedAirport loaded from GeoJSON files
"""
import os.path
import json
import yaml
import logging

from .airport import AirportBase
from emitpy.parameters import DATA_DIR

SYSTEM_DIRECTORY = os.path.join(DATA_DIR, "managedairport")

logger = logging.getLogger("GeoJSONAirport")


# ################################
# GEOJSON AIRPORT
#
#
class GeoJSONAirport(AirportBase):
    """
    Airport represetation
    """
    def __init__(self, icao: str, iata: str, name: str, city: str, country: str, region: str, lat: float, lon: float, alt: float):
        AirportBase.__init__(self, icao=icao, iata=iata, name=name, city=city, country=country, region=region, lat=lat, lon=lon, alt=alt)
        self.airport_base = None
        self.taxiways_geo = None
        self.ramps_geo = None
        self.service_roads_geo = None
        self.service_stops_geo = None
        self.data = None
        self.loaded = False

    def loadFromFile(self):
        self.airport_base = os.path.join(SYSTEM_DIRECTORY, self.icao)
        airport_df = os.path.join(self.airport_base, "airport.yaml")
        if os.path.exists(airport_df):
            self.data = yaml.safe_load(airport_df)

        logger.debug(":loadFromFile: loaded")
        return [True, "GeoJSONAirport::loadFromFile: loaded"]


    def loadRamps(self):
        self.loadGeometries("parkings.geojson")

        if self.data is not None:
            self.ramps_geo = self.data
            self.data = None
            logger.info(":loadRamps: added %d features.", len(self.ramps_geo["features"]))

        logger.debug(":loadRamps: added %d parkings", len(self.ramps.keys()))
        return [True, "GeoJSONAirport::loadRamps loaded"]

    def loadTaxiways(self):
        self.loadGeometries("taxiways.geojson")

        if self.data is not None:
            self.taxiways_geo = self.data
            self.data = None
            logger.info(":loadTaxiways: added %d features.", len(self.taxiways_geo["features"]))

        logger.info(":loadTaxiways: added %d nodes, %d edges.", len(self.taxiways.vert_dict), len(self.taxiways.edges_arr))
        return [True, "GeoJSONAirport::loadTaxiways loaded"]

    def loadServiceRoads(self):
        self.loadGeometries("serviceroads.geojson")

        if self.data is not None:  # parse runways
            self.service_roads_geo = self.data
            self.data = None
            logger.info(":loadServiceRoads: added %d features.", len(self.service_roads_geo["features"]))

        logger.info(":loadServiceRoads: added %d nodes, %d edges.", len(self.service_roads.vert_dict), len(self.service_roads.edges_arr))
        return [True, "GeoJSONAirport::loadServiceNetwork loaded"]


    def loadPOIS(self):
        status = self.loadServiceDestinations()

        if not status[0]:
            return status

        logger.debug(":loadPOIS: loaded")
        return [True, "GeoJSONAirport::loadPOIS loaded"]


    def loadServiceDestinations(self):
        self.loadGeometries("servicepois.geojson")

        if self.data is not None:  # parse runways
            self.service_stops_geo = self.data
            self.data = None
            logger.info(":loadServiceDestinations: added %d features.", len(self.service_stops_geo["features"]))


        logger.debug(":loadServiceDestinations: added %d service destinations", len(self.service_destinations.keys()))
        return [True, "GeoJSONAirport::loadServiceDestination loaded"]
