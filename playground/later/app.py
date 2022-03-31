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

logger = logging.getLogger("App")


class App:
    """
    """
    def __init__(self, airport):
        self.airport = airport
        self.managedAirport = None
        self.airspace = None


    def init(self):
        logger.debug("..loading managed airport..")
        self.managedAirport = XPAirport(
            icao=self.airport["ICAO"],
            iata=self.airport["IATA"],
            name=self.airport["name"],
            city=self.airport["city"],
            country=self.airport["country"],
            region=self.airport["regionName"],
            lat=self.airport["lat"],
            lon=self.airport["lon"],
            alt=self.airport["elevation"])
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

