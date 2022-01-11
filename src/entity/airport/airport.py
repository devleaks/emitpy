"""
Different types of airports, depending on their status in the simulation.

- AirportBase: Simple, regular destination
- Airport: Main airport in simulation.
"""
import logging

from ..graph import Graph
from ..geo import Location

logger = logging.getLogger("Airport")


# ################################@
# AIRPORT BASE
#
#
class AirportBase(Location):
    """
    An AirportBase is a location for flight departure and arrival.

    """
    def __init__(self, icao: str, iata: str, name: str, city: str, country: str, region: str, lat: float, lon: float, alt: float):
        Location.__init__(self, name, city, country, lat, lon, alt)
        self.icao = icao
        self.iata = iata
        self.region = region

        self._rawdata = {}
        self.airlines = {}
        self.routes = {}

    def loadFromFile(self):
        return [False, "no load implemented"]


# ################################@
# AIRPORT
#
#
class Airport(AirportBase):
    """
    An ManagedAirport is an airport as it appears in the simulation software.
    """
    def __init__(self, icao: str, iata: str, name: str, city: str, country: str, region: str, lat: float, lon: float, alt: float):
        AirportBase.__init__(self, icao=icao, iata=iata, name=name, city=city, country=country, region=region, lat=lat, lon=lon, alt=alt)
        self.procedures = None
        self.runways = {}
        self.taxiways = Graph()
        self.parkings = {}
        self.service_roads = Graph()
        self.service_destinations = {}

    def load(self):
        status = self.loadFromFile()

        if not status[0]:
            return [False, status[1]]

        status = self.loadRunways()
        if not status[0]:
            return [False, status[1]]

        status = self.loadParkings()
        if not status[0]:
            return [False, status[1]]

        status = self.loadTaxiways()
        if not status[0]:
            return [False, status[1]]

        status = self.loadServiceRoads()
        if not status[0]:
            return [False, status[1]]

        status = self.loadServiceDestinations()
        if not status[0]:
            return [False, status[1]]

        return [True, "Airport::load loaded"]


    def loadFromFile(self):
        return [False, "no load implemented"]

    def loadProcedures(self):
        return [False, "no load implemented"]

    def loadRunways(self):
        return [False, "no load implemented"]

    def loadTaxiways(self):
        return [False, "no load implemented"]

    def loadParkings(self):
        return [False, "no load implemented"]

    def loadServiceRoads(self):
        return [False, "no load implemented"]

    def loadServiceDestinations(self):
        return [False, "no load implemented"]
