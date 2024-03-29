"""
ManagedAirport loaded from GeoJSON files
HISTORICAL. NOT MAINTAINED. AS USED IN JAVASCRIPT VERSION OF EMITJS (circa 2019)
References where loaded from (mostly handcrafted) GeoJSON files.
Could still be used, but needs adaptation.
"""

import os.path
import logging
import json
import yaml

from .airport import ManagedAirportBase
from emitpy.parameters import DATA_DIR, MANAGED_AIRPORT_DIR

logger = logging.getLogger("GeoJSONAirport")


# ################################
# GEOJSON AIRPORT
#
#
class GeoJSONAirport(ManagedAirportBase):
    """
    Airport represetation
    """

    def __init__(
        self,
        icao: str,
        iata: str,
        name: str,
        city: str,
        country: str,
        region: str,
        lat: float,
        lon: float,
        alt: float,
    ):
        ManagedAirportBase.__init__(
            self,
            icao=icao,
            iata=iata,
            name=name,
            city=city,
            country=country,
            region=region,
            lat=lat,
            lon=lon,
            alt=alt,
        )
        self.airport_base = None
        self.taxiways_geo = None
        self.ramps_geo = None
        self.service_roads_geo = None
        self.service_stops_geo = None
        self.data = None
        self.loaded = False

    def loadFromFile(self):
        self.airport_base = MANAGED_AIRPORT_DIR
        airport_df = os.path.join(self.airport_base, "airport.yaml")
        if os.path.exists(airport_df):
            self.data = yaml.safe_load(airport_df)

        logger.debug("loaded")
        return [True, "GeoJSONAirport::loadFromFile: loaded"]

    def loadRamps(self):
        self.loadGeometries("parkings.geojson")

        if self.data is not None:
            self.ramps_geo = self.data
            self.data = None
            logger.info("added %d features.", len(self.ramps_geo["features"]))

        logger.debug("added %d parkings", len(self.ramps.keys()))
        return [True, "GeoJSONAirport::loadRamps loaded"]

    def loadTaxiways(self):
        self.loadGeometries("taxiways.geojson")

        if self.data is not None:
            self.taxiways_geo = self.data
            self.data = None
            logger.info("added %d features.", len(self.taxiways_geo["features"]))

        logger.info(
            "added %d nodes, %d edges.",
            len(self.taxiways.vert_dict),
            len(self.taxiways.edges_arr),
        )
        return [True, "GeoJSONAirport::loadTaxiways loaded"]

    def loadServiceRoads(self):
        self.loadGeometries("serviceroads.geojson")

        if self.data is not None:  # parse runways
            self.service_roads_geo = self.data
            self.data = None
            logger.info("added %d features.", len(self.service_roads_geo["features"]))

        logger.info(
            "added %d nodes, %d edges.",
            len(self.service_roads.vert_dict),
            len(self.service_roads.edges_arr),
        )
        return [True, "GeoJSONAirport::loadServiceNetwork loaded"]

    def loadPOIS(self):
        status = self.loadServicePOIS()

        if not status[0]:
            return status

        logger.debug("loaded")
        return [True, "GeoJSONAirport::loadPOIS loaded"]

    def loadServicePOIS(self):
        self.loadJSONOrYAMLFromFile("servicepois.geojson")

        if self.data is not None:  # parse runways
            self.service_stops_geo = self.data
            self.data = None
            logger.info("added %d features.", len(self.service_stops_geo["features"]))

        logger.debug("added %d service destinations", len(self.service_pois.keys()))
        return [True, "GeoJSONAirport::loadServicePOIS loaded"]
