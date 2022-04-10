"""
Airport Manager is a container for business and operations.
"""
import os
import yaml
import csv
import logging
import random
import importlib
import operator

from .airline import Airline
from ..airport import Airport
from ..parameters import DATA_DIR

SYSTEM_DIRECTORY = os.path.join(DATA_DIR, "managedairport")


logger = logging.getLogger("AirportManager")


class AirportManager:

    def __init__(self, icao):
        self.icao = icao
        self.airlines = {}
        self.airport_base_path = None
        self.data = None
        self.airline_route_frequencies = None
        self.airline_frequencies = None
        self.service_vehicles = {}
        self.vehicle_number = 0

    def load(self):
        """
        Loads airport manager data from files.
        """
        status = self.loadFromFile()
        if not status[0]:
            return status

        status = self.loadAirRoutes()
        if not status[0]:
            return status

        return [False, "AirportManager::loaded"]


    def loadFromFile(self):
        """
        Loads an airport's data file and place its content in self.data
        """
        self.airport_base_path = os.path.join(SYSTEM_DIRECTORY, self.icao)
        business = os.path.join(self.airport_base_path, "airport.yaml")
        if os.path.exists(business):
            with open(business, "r") as fp:
                self.data = yaml.safe_load(fp)
            logger.warning(f":file: {business} loaded")
            return [True, "AirportManager::loadFromFile: loaded"]
        logger.warning(f":file: {business} not found")
        return [False, "AirportManager::loadFromFile file %s not found", business]


    def loadAirRoutes(self):
        """
        Loads this airport's air routes from a data file.
        """
        routes = os.path.join(self.airport_base_path, "airline-routes.csv")
        file = open(routes, "r")
        csvdata = csv.DictReader(file)  # AIRLINE CODE,AIRPORT
        cnt = 0
        for row in csvdata:
            airline = Airline.findIATA(row["AIRLINE CODE"])
            if airline is not None:
                if airline.iata not in self.airlines.keys():
                    self.airlines[airline.icao] = airline
                airport = Airport.findIATA(row["AIRPORT"])
                if airport is not None:
                    airline.addRoute(airport)
                    airport.addAirline(airline)
                    cnt = cnt + 1
                else:
                    logger.warning(f":loadAirRoutes: airport {row['AIRPORT']} not found")
            else:
                logger.warning(f":loadAirRoutes: airline {row['AIRLINE CODE']} not found")
        file.close()
        logger.debug(":loadAirRoutes: loaded %d airline routes for %d airlines" % (cnt, len(self.airlines)))

        fn = os.path.join(self.airport_base_path, "airline-frequencies.csv")
        if os.path.exists(fn):
            self.airline_frequencies = {}
            with open(fn, "r") as file:
                data = csv.DictReader(file)  # AIRLINE CODE,AIRPORT
                for row in data:
                    self.airline_frequencies[row["AIRLINE CODE"]] = int(row["COUNT"])
                logger.debug(":loadAirRoutes: airline-frequencies loaded")

        fn = os.path.join(self.airport_base_path, "airline-route-frequencies.csv")
        if os.path.exists(fn):
            self.airline_route_frequencies = {}
            with open(fn, "r") as file:
                data = csv.DictReader(file)  # AIRLINE CODE,AIRPORT
                for row in data:
                    if row["AIRLINE CODE"] not in self.airline_route_frequencies:
                        self.airline_route_frequencies[row["AIRLINE CODE"]] = {}

                    if row["AIRPORT"] not in self.airline_route_frequencies[row["AIRLINE CODE"]]:
                        self.airline_route_frequencies[row["AIRLINE CODE"]][row["AIRPORT"]] = 0
                    self.airline_route_frequencies[row["AIRLINE CODE"]][row["AIRPORT"]] = self.airline_route_frequencies[row["AIRLINE CODE"]][row["AIRPORT"]] + int(row["COUNT"])
                logger.debug(":loadAirRoutes: airline-route-frequencies loaded")

        logger.debug(":loadAirRoutes: loaded")
        return [True, "AirportManager::loadAirRoutes: loaded"]


    def getAirlineCombo(self):
        """
        Builds a list of (code, description) pairs for all airlines operating at this airport.
        """
        return [(a.iata, a.orgId) for a in sorted(self.airlines.values(), key=operator.attrgetter('orgId'))]


    def getAirrouteCombo(self, airline = None):
        """
        Builds a list of (code, description) pairs for all routes for the airline operating at this airport.
        """
        routes = set()
        if airline is None:
            for al in self.airline_route_frequencies.values():
                routes = routes.union(al.keys())
        else:

            routes = set(self.airline_route_frequencies[airline].keys())
        # return routes
        apts = list(filter(lambda a: a.iata in routes, Airport._DB_IATA.values()))
        return [(a.iata, a.display_name) for a in sorted(apts, key=operator.attrgetter('display_name'))]


    def selectRandomAirline(self):
        """
        Selects a random airline operating at this airport.
        """
        aln = None
        if self.airline_frequencies is not None:
            a = a = random.choices(population=list(self.airline_frequencies.keys()), weights=list(self.airline_frequencies.values()))
            aln = Airline.findIATA(a[0])
            if aln is not None:
                logger.debug(f":selectRandomAirline: with density: {aln.icao}({aln.iata})")
            else:
                logger.warning(f":selectRandomAirline: with density: {a[0]} not found")
        else:
            a = random.choice(list(self.airlines.keys()))
            aln = Airline.find(a)
            logger.debug(f":selectRandomAirline: {a}")
        return aln


    def selectRandomAirroute(self, airline: Airline = None):
        """
        Selects a random air route from this airport. If no airline is supplied,
        selects first a random airline operating at this airport.
        """
        aln = airline if airline is not None else self.selectRandomAirline()
        apt = None
        if self.airline_route_frequencies is not None:
            aptlist = self.airline_route_frequencies[aln.iata]
            a = random.choices(population=list(aptlist.keys()), weights=list(aptlist.values()))
            apt = Airport.findIATA(a[0])
            if apt is None:
                logger.warning(f":selectRandomAirroute: with density: {a[0]} not found")
            else:
                logger.debug(f":selectRandomAirroute: with density: {apt.icao}({apt.iata})")
        else:
            a = random.choice(list(aln.routes.keys()))
            apt = Airport.find(a)
            logger.debug(f":selectRandomAirroute: {a}")
        return (aln, apt)

    def hub(self, airport, airline):
        """
        Defines that an airline is using this airport as a hub.
        """
        airport.addHub(airline)
        airline.addHub(airport)


    def selectServiceVehicle(self, operator: "Company", service: "Service", model: str=None, registration: str = None, use: bool=True):
        """
        Selects a service vehicle for ground support.
        The airport manager keeps a list of all vehicle and their use.
        It will return a vehicle available at the datetime of the request for a supplied duration.

        :param      operator:      The operator
        :type       operator:      { type_description }
        :param      service:       The service
        :type       service:       { type_description }
        :param      model:         The model
        :type       model:         str
        :param      registration:  The registration
        :type       registration:  str
        :param      use:           The use
        :type       use:           bool
        """
        vname = registration
        if vname is None:
            sty = type(service).__name__[0:3].upper()
            self.vehicle_number = self.vehicle_number + 1
            vname = sty + ("%03d" % self.vehicle_number)
        if vname not in self.service_vehicles.keys():
            if type(service).__name__ == "Mission":  # special treatment, may be missions should be "Service"?
                vcl = "MissionVehicle"
            else:
                vcl = type(service).__name__.replace("Service", "Vehicle")
            if model is not None:
                model = model.replace("-", "_")  # now model is snake_case
                mdl = ''.join(word.title() for word in model.split('_'))  # now model is CamelCase
                vcl = vcl + mdl
            logger.debug(f":selectServiceVehicle: creating {vcl} {vname}")
            servicevehicleclasses = importlib.import_module(name=".service.servicevehicle", package="emitpy")
            if hasattr(servicevehicleclasses, vcl):
                vehicle = getattr(servicevehicleclasses, vcl)(registration=vname, operator=operator)  ## getattr(sys.modules[__name__], str) if same module...
                vehicle.setICAO24(AirportManager.randomICAO24(15))  # starts with F
                self.service_vehicles[vname] = vehicle
                logger.debug(f":selectServiceVehicle: added {vname}")
                if use:
                    logger.debug(f":selectServiceVehicle: using {vname}")
                    service.setVehicle(vehicle)
                return vehicle
            else:
                logger.warning(f":selectServiceVehicle: no class {vcl}")
        else:
            vehicle = self.service_vehicles[vname]
            if use:
                logger.debug(f":selectServiceVehicle: reusing {vname}")
                service.setVehicle(vehicle)
            return vehicle

        logger.debug(f":selectServiceVehicle: returning no vehicle?")
        return None

    @staticmethod
    def randomICAO24(root: int = None):
        """
        Create a random ICOA 24 bit address for ADS-B broadcast.
        If a root value is supplied, it is used as the first character/number.
        The rot value must be an integer value in [0-15] range.
        This allows for artificial address separation and easy vehicle identification
        during generation and simulation.

        :param      root:  The root
        :type       root:  int
        """
        # can set the first number form 1 to F
        if root is not None:
            if root < 1:
                root = 1
            if root > 15:
                root = 15
            return f"{root:x}{random.getrandbits(20):x}"

        return f"{random.getrandbits(24):x}"



