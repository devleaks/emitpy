"""
Airport Manager is a container for business and operations.
"""
import os
import yaml
import json
import csv
import logging
import random
import importlib
import operator

from datetime import datetime, timedelta, timezone

from .airline import Airline
from .company import Company
from emitpy.airport import Airport
from emitpy.resource import AllocationTable

from emitpy.constants import ARRIVAL, DEPARTURE, REDIS_DATABASE, REDIS_TYPE, ID_SEP, FLIGHT_TIME_FORMAT
from emitpy.parameters import DATA_DIR, MANAGED_AIRPORT
from emitpy.utils import key_path, Timezone
from emitpy.emit import EmitMeta

MANAGED_AIRPORT_DIRECTORY = os.path.join(DATA_DIR, "managedairport")


logger = logging.getLogger("AirportManager")


class AirportManager:

    def __init__(self, icao, operator: "Company", app):
        self.icao = icao
        self.operator = operator
        self._app = app

        self.companies = {}
        self.people = {}

        self.airlines = {}
        self.airline_frequencies = None
        self.airline_routes = None
        self.airline_route_frequencies = None

        self.vehicle_number = 200
        self.vehicle_by_type = {}
        self.service_vehicles = {}
        self.vehicle_allocator = None

        self.ramps = {}
        self.ramp_allocator = None

        self.runways = {}
        self.runway_allocator = None

        self.aircrafts = {}   # container for aircrafts encountered during simulation, key is registration.
        self.flights = {}     # container for flights created during simalation, can be used to build flight board.

        self.airport_base_path = None
        self.data = None


    def load(self):
        """
        Loads airport manager data from files.
        """
        status = self.loadFromFile()
        if not status[0]:
            return status

        status = self.loadCompanies()
        if not status[0]:
            return status

        status = self.loadAirRoutes()
        if not status[0]:
            return status

        status = self.loadServiceVehicles()
        if not status[0]:
            return status

        return [True, "AirportManager::loaded"]


    def loadFromFile(self):
        """
        Loads an airport's data file and place its content in self.data
        """
        self.airport_base_path = os.path.join(MANAGED_AIRPORT_DIRECTORY, self.icao)
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
        routes = os.path.join(self.airport_base_path, "airlines", "airline-routes.csv")
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

        fn = os.path.join(self.airport_base_path, "airlines", "airline-frequencies.csv")
        if os.path.exists(fn):
            self.airline_frequencies = {}
            with open(fn, "r") as file:
                data = csv.DictReader(file)  # AIRLINE CODE,AIRPORT
                for row in data:
                    self.airline_frequencies[row["AIRLINE CODE"]] = int(row["COUNT"])
                logger.debug(":loadAirRoutes: airline-frequencies loaded")

        fn = os.path.join(self.airport_base_path, "airlines", "airline-route-frequencies.csv")
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


    def loadCompanies(self):
        """
        Loads companies.

        :returns:   { description_of_the_return_value }
        :rtype:     { return_type_description }
        """
        self.airport_base_path = os.path.join(MANAGED_AIRPORT_DIRECTORY, self.icao)
        companies = os.path.join(self.airport_base_path, "services", "companies.yaml")
        if os.path.exists(companies):
            with open(companies, "r") as fp:
                self.data = yaml.safe_load(fp)
            logger.warning(f":file: {companies} loaded")
            for k, c in self.data.items():
                self.companies[k] = Company(orgId=c["orgId"],
                                            classId=c["classId"],
                                            typeId=c["typeId"],
                                            name=c["name"])
            return [True, f"AirportManager::loadCompanies loaded {self.companies.keys()}"]
        return [False, f"AirportManager::loadCompanies file {companies} not found"]


    def getCompaniesCombo(self, classId: str = None, typeId: str = None):
        """
        Builds (key, display name) pairs for companies, filtered by classId
        and/or typeId if supplied.

        :param      classId:  The class identifier
        :type       classId:  str
        :param      typeId:   The type identifier
        :type       typeId:   str

        :returns:   The companies combo.
        :rtype:     { return_type_description }
        """
        companies = self.companies.values()
        if classId is not None:
            companies = filter(lambda c: c.classId == classId , companies)
        if typeId is not None:
            companies = filter(lambda c: c.typeId == typeId , companies)
        return list([(c.getId(), c.name) for c in companies])


    def loadServiceVehicles(self):
        """
        Loads service vehicle fleet and creates vehicle.
        """
        self.airport_base_path = os.path.join(MANAGED_AIRPORT_DIRECTORY, self.icao)
        business = os.path.join(self.airport_base_path, "services", "servicevehiclefleet.yaml")
        if os.path.exists(business):
            with open(business, "r") as fp:
                self.data = yaml.safe_load(fp)
            logger.warning(f":file: {business} loaded")
            servicevehicleclasses = importlib.import_module(name=".service.servicevehicle", package="emitpy")
            for vtype in self.data["ServiceVehicleFleet"]:
                (vcl, vqty) = list(vtype.items())[0]
                logger.debug(f":loadServiceVehicles: doing {vtype}..")
                names = vcl.split("Vehicle")
                vname_root = names[0][0:3].upper()
                if len(names) > 1 and names[1] != "":
                    vname_root = vname_root + names[1][0:2].upper()
                else:
                    vname_root = vname_root + "SV"  # "standard vehicle"
                if hasattr(servicevehicleclasses, vcl):
                    for idx in range(int(vqty)):
                        vname = f"{vname_root}{idx:03d}"
                        vehicle = getattr(servicevehicleclasses, vcl)(registration=vname, operator=self.operator)  ## getattr(sys.modules[__name__], str) if same module...
                        vehicle.setICAO24(AirportManager.randomICAO24(15))  # starts with F like fleet.
                        self.service_vehicles[vname] = vehicle
                        if vcl not in self.vehicle_by_type:
                            self.vehicle_by_type[vcl] = []
                        self.vehicle_by_type[vcl].append(vehicle)
                        # logger.debug(f":loadServiceVehicles: ..added {vname}")
                else:
                    logger.warning(f":loadServiceVehicles: vehicle type {vcl} not found")

            self.setServiceVehicles(self.service_vehicles)
            logger.debug(f":loadServiceVehicles: ..done")
            return [True, "AirportManager::loadServiceVehicles: loaded"]


        logger.warning(f":loadServiceVehicles: {business} not found")
        return [False, "AirportManager::loadServiceVehicles file %s not found", business]



    def selectServiceVehicle(self, operator: "Company", service: "Service", reqtime: "datetime", reqend: "datetime" = None,
                             model: str=None, registration: str = None, use: bool=True):
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
        def is_default_model(model):
            if model is None:
                return True

            DEFAULT_VEHICLE = ":default"
            return len(model) > len(DEFAULT_VEHICLE) and model[:-len(DEFAULT_VEHICLE)] != DEFAULT_VEHICLE

        vname = registration
        svc_name = (type(service).__name__).replace("Service", "")

        if vname is not None and vname in self.service_vehicles.keys():
            vehicle = self.service_vehicles[vname]
            if use: # there is no check that the vehicle is available
                if reqend is None:
                    reqend = reqtime + timedelta(seconds=service.duration())
                res = self.vehicle_allocator.book(vname, reqtime, reqend, service.getId())
                service.setVehicle(vehicle)
                logger.debug(f":selectServiceVehicle: reusing {vehicle.registration}")
            return vehicle

        # is there a vehicle of same type available:
        if type(service).__name__ == "Mission":  # special treatment, may be missions should be "Service"?
            vcl = "MissionVehicle"
            vcl_short = "MIS"
        else:
            vcl = svc_name + "Vehicle"
            vcl_short = svc_name[0:3].upper()

        if is_default_model(model):
            vcl_short = vcl_short + "SV"  # Standard Vehicle
            logger.debug(f":selectServiceVehicle: without model is {vcl}, {vcl_short}")
        else:
            logger.debug(f":selectServiceVehicle: model is {model}")
            model = model.replace("-", "_")  # now model is snake_case
            mdl = ''.join(word.title() for word in model.split('_'))  # now model is CamelCase
            vcl = vcl + mdl
            vcl_short = vcl_short + mdl[0:2].upper()
            logger.debug(f":selectServiceVehicle: with model is {vcl}, {vcl_short}")

        logger.debug(f":selectServiceVehicle: searching for available {vcl}, {vcl_short}")

        if vcl in self.vehicle_by_type:
            idx = 0
            vehicle = None
            res = None
            while vehicle is None and idx < len(self.vehicle_by_type[vcl]):
                v = self.vehicle_by_type[vcl][idx]
                if reqend is None:
                    reqend = reqtime + timedelta(seconds=service.duration())
                if self.vehicle_allocator.isAvailable(v.getId(), reqtime, reqend):
                    service.setVehicle(v) # need to set vehicle to get service.getId() that includes vehicle
                    res = self.vehicle_allocator.book(v.getId(), reqtime, reqend, service.getId())
                    vehicle = v
                idx = idx + 1

            if vehicle is not None:
                logger.debug(f":selectServiceVehicle: found {vcl}, reusing {vehicle.registration}")
            return vehicle
        else:
            logger.debug(f":selectServiceVehicle: no {vcl} available")

        # need to create one...
        if vname is None:  # else uses supplied registration
            self.vehicle_number = self.vehicle_number + 1
            vname = f"{vcl_short}{self.vehicle_number:03d}"
            logger.debug(f":selectServiceVehicle: no registration supplied, creating {vname}..")
        else:
            logger.debug(f":selectServiceVehicle: vehicle {vname} does not exist, creating..")
        if vname not in self.service_vehicles.keys():
            servicevehicleclasses = importlib.import_module(name=".service.servicevehicle", package="emitpy")
            if hasattr(servicevehicleclasses, vcl):
                vehicle = getattr(servicevehicleclasses, vcl)(registration=vname, operator=operator)  ## getattr(sys.modules[__name__], str) if same module...
                vehicle.setICAO24(AirportManager.randomICAO24(10))  # starts with A
                self.service_vehicles[vname] = vehicle
                if vcl not in self.vehicle_by_type:
                    self.vehicle_by_type[vcl] = []
                self.vehicle_by_type[vcl].append(vehicle)
                #  need to add it to alloc table and book it
                self.vehicle_allocator.add(vehicle)
                if reqend is None:
                    reqend = reqtime + timedelta(seconds=service.duration())
                res = self.vehicle_allocator.book(vehicle.getId(), reqtime, reqend, service.getId())
                logger.debug(f":selectServiceVehicle: ..added {vname}")
                if use:
                    logger.debug(f":selectServiceVehicle: using {vname}")
                    service.setVehicle(vehicle)
                return vehicle
            else:
                logger.warning(f":selectServiceVehicle: no class {vcl}")
        else:
            logger.warning(f":selectServiceVehicle: already exist {vname}?")

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


    def setServiceVehicles(self, vehicles):
        self.service_vehicles = vehicles
        logger.debug(f":selectServiceVehicles: allocating..")
        self.vehicle_allocator = AllocationTable(resources=self.service_vehicles.values(),
                                                 name="service-vehicles")
        logger.debug(f":service_vehicles: ..done")


    def bookVehicle(self, vehicle: "ServiceVehicle", reqtime: "datetime", reqduration: int, reason: str):
        reqend = reqtime + timedelta(minutes=reqduration)
        avail = self.vehicle_allocator.isAvailable(ramp.getId(), reqtime, reqend)
        if avail:
            self.vehicle_allocator.book(ramp.getId(), reqtime, reqend, reason)
        return avail


    def setRamps(self, ramps):
        self.ramps = ramps
        logger.debug(f":setRamps: allocating..")
        self.ramp_allocator = AllocationTable(resources=self.ramps.values(),
                                              name="ramps")
        logger.debug(f":setRamps: ..done")


    def bookRamp(self, ramp: "Ramp", reqtime: "datetime", reqduration: int, reason: str):
        reqend = reqtime + timedelta(minutes=reqduration)
        avail = self.ramp_allocator.isAvailable(ramp.getId(), reqtime, reqend)
        if avail:
            self.ramp_allocator.book(ramp.getId(), reqtime, reqend, reason)
        return avail


    def setRunways(self, runways):
        self.runways = runways
        logger.debug(f":setRunways: allocating..")
        self.runway_allocator = AllocationTable(resources=[], name="runways")
        for rwy in self.runways.values():
            rwy_id = rwy.getResourceId()
            if rwy_id not in self.runway_allocator.resources.keys():
                self.runway_allocator.addNamedResource(rwy, rwy_id)
        logger.debug(f":setRunways: resources added: {self.runway_allocator.resources.keys()}")
        logger.debug(f":setRunways: ..done")


    def bookRunway(self, runway: "Runway", reqtime: "datetime", reqduration: int, reason: str):
        reqend = reqtime + timedelta(minutes=reqduration)
        avail = self.runway_allocator.isAvailable(runway.getResourceId(), reqtime, reqend)
        if avail:
            self.runway_allocator.book(runway.getResourceId(), reqtime, reqend, reason)
        return avail

    def saveAllocators(self, redis):
        self.vehicle_allocator.save(redis)
        self.ramp_allocator.save(redis)
        self.runway_allocator.save(redis)


    def allFlights(self, redis):
        keys = redis.keys(REDIS_DATABASE.FLIGHTS.value + "*")
        items = []
        if items is not None and len(keys) > 0:
            for f in keys:
                items.append(ID_SEP.join(f.decode("UTF-8").split(ID_SEP)[:-1]))
            return set(items)
        return items


    def allMissions(self, redis):
        keys = redis.keys(REDIS_DATABASE.MISSIONS.value + "*")
        items = []
        if keys is not None and len(keys) > 0:
            for f in keys:
                items.append(ID_SEP.join(f.decode("UTF-8").split(ID_SEP)[:-1]))
            return set(items)
        return items


    def allServiceForFlight(self, redis, flight_id: str):
        items = []
        flight_meta = EmitMeta(redis=redis, flight_id=flight_id)

        if flight_meta.is_arrival:  # in minutes:
            before = 60
            after = 180
        else:
            before = 180
            after = 60
        et_min = flight_meta.scheduled - timedelta(minutes=before)
        et_max = flight_meta.scheduled + timedelta(minutes=after)
        logger.debug(f":allServiceForFlight: {ARRIVAL if flight_meta.is_arrival else DEPARTURE} at {et_move}")
        logger.debug(f":allServiceForFlight: trying services between {et_min} and {et_max}")

        # 2 search for all services at that ramp, "around" supplied ETA/ETD.
        for k in keys:
            k = k.decode("UTF-8")
            karr = k.split(ID_SEP)
            dt = datetime.fromisoformat(karr[3].replace(".", ":"))
            logger.debug(f":allServiceForFlight: testing {dt}...")
            if dt > et_min and dt < et_max:
                items.append(ID_SEP.join(k.split(ID_SEP)[:-1]))
        return set(items)


    def allServiceOfType(self, redis, service_type: str):
        service_class = service_type[0].upper() + service_type[1:].lower() + "Service"  # @todo: Hum.
        ks = key_path(REDIS_DATABASE.SERVICES.value, service_class, "*")
        # logger.debug(f":allServiceOfType: trying {ks}")
        keys = redis.keys(ks)
        items = []
        if keys is not None and len(keys) > 0:
            for f in keys:
                items.append(ID_SEP.join(f.decode("UTF-8").split(ID_SEP)[:-1]))
            return set(items)
        return items


    def allServiceForRamp(self, redis, ramp_id: str):
        ks = key_path(REDIS_DATABASE.SERVICES.value, "*", ramp_id, "*")
        logger.debug(f":allServiceForRamp: trying {ks}")
        keys = redis.keys(ks)
        items = []
        if keys is not None and len(keys) > 0:
            for f in keys:
                items.append(ID_SEP.join(f.decode("UTF-8").split(ID_SEP)[:-1]))
            return set(items)
        return items
