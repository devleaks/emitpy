import logging

from ..airspace import XPAirspace, Metar
from ..business import Airline, Company
from ..aircraft import AircraftType, AircraftPerformance, Aircraft
from ..airport import Airport, AirportBase, XPAirport
from ..business import AirportManager


logger = logging.getLogger("ManagedAirport")


class ManagedAirport:
    """
    Wrapper class to load all managed airport parts.
    """

    def __init__(self, airport):
        self._this_airport = airport
        self.airport = None

    def init(self):

        airspace = XPAirspace()
        logger.debug("loading airspace..")
        airspace.load()
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

        logger.debug("loading managed airport..")

        logger.debug("..loading airport manager..")
        manager = AirportManager(icao=self._this_airport["ICAO"])
        manager.load()

        logger.debug("..loading managed airport..")
        self.airport = XPAirport(
            icao=self._this_airport["ICAO"],
            iata=self._this_airport["IATA"],
            name=self._this_airport["name"],
            city=self._this_airport["city"],
            country=self._this_airport["country"],
            region=self._this_airport["regionName"],
            lat=self._this_airport["lat"],
            lon=self._this_airport["lon"],
            alt=self._this_airport["elevation"])
        ret = self.airport.load()
        if not ret[0]:
            print("Managed airport not loaded")

        self.airport.setAirspace(airspace)
        self.airport.setManager(manager)
        logger.debug("..done")

        self.update_metar()
        return (True, "ManagedAirport::init done")


    def update_metar(self):
        logger.debug("collecting METAR..")
        # Prepare airport for each movement
        metar = Metar(icao=self._this_airport["ICAO"])
        self.airport.setMETAR(metar=metar)  # calls prepareRunways()
        logger.debug("..done")
