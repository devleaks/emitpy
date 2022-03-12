"""
Application container
"""
from entity.airspace import XPAirspace, Metar
from entity.business import Airline
from entity.aircraft import AircraftType, AircraftPerformance, Aircraft
from entity.flight import Arrival, Departure, ArrivalMove, DepartureMove
from entity.airport import Airport, AirportBase, XPAirport
from entity.emit import Emit, BroadcastToFile, ADSB
from entity.business import AirportManager
from entity.service import FuelService, ServiceMove


import logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("App")


class App:
    """
    """
    def __init__(self, airport):
        self.airport = airport


    def init(self):
        logger.debug("..loading managed airport..")
        self.managedAirport = XPAirport(
            icao=airport["ICAO"],
            iata=airport["IATA"],
            name=airport["name"],
            city=airport["city"],
            country=airport["country"],
            region=airport["regionName"],
            lat=airport["lat"],
            lon=airport["lon"],
            alt=airport["elevation"])
        ret = self.managedAirport.load()
        if not ret[0]:
            print(f":App: managed airport not loaded: {ret}")
        logger.debug("..done")

        logger.debug("loading airspace..")
        self.airspace = XPAirspace()
        self.airspace.load()
        logger.debug("..done")

        logger.debug("loading airport..")
        Airport.loadAll()
        logger.debug("..done")

        logger.debug("loading airlines..")
        Airline.loadAll()
        logger.debug("..done")

        logger.debug("loading aircrafts..")
        AircraftType.loadAll()
        AircraftPerformance.loadAll()
        logger.debug("..done")

