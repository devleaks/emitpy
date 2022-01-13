# Airport as defined in X-Plane
#
import os.path
import json
import yaml
import logging

from .airport import Airport
from ..parameters import DATA_DIR

SYSTEM_DIRECTORY = os.path.join(DATA_DIR, "managedairport")

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
        self.airport_base = None
        self.taxiways_geo = None
        self.parkings_geo = None
        self.service_roads_geo = None
        self.service_stops_geo = None
        self.data = None
        self.loaded = False

    def loadFromFile(self):
        self.airport_base = os.path.join(SYSTEM_DIRECTORY, self.icao)
        airport_df = os.path.join(self.airport_base, "airport.yaml")

        logging.debug("GeoJSONAirport::loadFromFile: loaded")
        return [True, "GeoJSONAirport::loadFromFile: loaded"]


    def loadFromFile2(self, name):
        df = os.path.join(self.airport_base, "geometries", name)

        if os.path.exists(df):
            with open(df, "r") as fp:
                if name[-5:] == ".yaml":
                    self.data = yaml.safe_load(fp)
                else:  # JSON or GeoJSON
                    self.data = json.load(fp)
        else:
            logger.warning("GeoJSONAirport::file: %s not found" % df)
            return [False, "GeoJSONAirport::loadRunways file %s not found", df]

        return [True, "GeoJSONAirport::file %s loaded" % name]

    def loadRunways(self):
        self.loadFromFile2("runways.yaml")

        if self.data is not None:  # parse runways
            pass

        logging.debug("GeoJSONAirport::loadRunways: added %d runways", len(self.runways.keys()))
        return [True, "GeoJSONAirport::loadRunways loaded"]

    def loadParkings(self):
        self.loadFromFile2("parkings.geojson")

        if self.data is not None:
            self.parkings_geo = self.data
            self.data = None
            logging.info("GeoJSONAirport::loadParkings: added %d features.", len(self.parkings_geo["features"]))

        logging.debug("GeoJSONAirport::loadParkings: added %d parkings", len(self.parkings.keys()))
        return [True, "GeoJSONAirport::loadParkings loaded"]

    def loadTaxiways(self):
        self.loadFromFile2("taxiways.geojson")

        if self.data is not None:
            self.taxiways_geo = self.data
            self.data = None
            logging.info("GeoJSONAirport::loadTaxiways: added %d features.", len(self.taxiways_geo["features"]))

        logging.info("GeoJSONAirport::loadTaxiways: added %d nodes, %d edges.", len(self.taxiways.vert_dict), len(self.taxiways.edges_arr))
        return [True, "GeoJSONAirport::loadTaxiways loaded"]

    def loadServiceRoads(self):
        self.loadFromFile2("serviceroads.geojson")

        if self.data is not None:  # parse runways
            self.service_roads_geo = self.data
            self.data = None
            logging.info("GeoJSONAirport::loadServiceRoads: added %d features.", len(self.service_roads_geo["features"]))

        logging.info("GeoJSONAirport::loadServiceRoads: added %d nodes, %d edges.", len(self.service_roads.vert_dict), len(self.service_roads.edges_arr))
        return [True, "GeoJSONAirport::loadServiceNetwork loaded"]

    def loadServiceDestinations(self):
        self.loadFromFile2("servicepois.geojson")

        if self.data is not None:  # parse runways
            self.service_stops_geo = self.data
            self.data = None
            logging.info("GeoJSONAirport::loadServiceDestinations: added %d features.", len(self.service_stops_geo["features"]))


        logging.debug("GeoJSONAirport::loadServiceDestinations: added %d service destinations", len(self.service_destinations.keys()))
        return [True, "GeoJSONAirport::loadServiceDestination loaded"]
