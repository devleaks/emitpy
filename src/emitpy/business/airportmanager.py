"""
Airport Manager is a container for business and operations.
"""
import os
from datetime import datetime, timedelta, timezone

import logging
import random
import importlib
import operator as py_operator
import csv
import yaml
from math import inf


from .airline import Airline
from .company import Company
from emitpy.airport import Airport
from emitpy.resource import AllocationTable
# from emitpy.service import FlightServices

from emitpy.constants import REDIS_DATABASE, REDIS_TYPE, REDIS_PREFIX, ID_SEP, REDIS_DB, EVENT_ONLY_SERVICE
from emitpy.constants import ARRIVAL, DEPARTURE, FLIGHT_TIME_FORMAT, DEFAULT_VEHICLE, DEFAULT_VEHICLE_SHORT, EQUIPMENT
from emitpy.parameters import MANAGED_AIRPORT_DIR
from emitpy.utils import key_path, rejson, rejson_keys, KebabToCamel
from emitpy.emit import ReEmit
# from emitpy.service import Service

logger = logging.getLogger("AirportManager")


class AirportManager:
    """
    The Airport Manager entity is responsible for managing the Managed Airport resources.
    It also supply the Managed Airport business data such as airlines operating at the Managed Airport,
    or air route frequencies.

    :param      icao:      ICAO code of the Managed Airport
    :type       icao:      { type_description }
    :param      operator:  Operating company for the Managed Airport
    :type       operator:  { type_description }
    """

    def __init__(self, icao, operator: Company):
        self.icao = icao
        self.operator = operator

        self.companies = {}
        self.people = {}

        self.airlines = {}
        self.airline_frequencies = None
        self.airline_routes = None
        self.airline_route_frequencies = None

        self.equipment_number = 200
        self.equipment_by_type = {}
        self.equipments = {}
        self.equipment_allocator = None

        self.ramps = {}
        self.ramp_allocator = None

        self.runways = {}
        self.runway_allocator = None

        self.aircrafts = {}   # container for aircrafts encountered during simulation, key is registration.
        self.flights = {}     # container for flights created during simalation, can be used to build flight board.

        self.data = None


    def load(self, redis = None):
        """
        Loads airport manager data from files.
        """
        status = self.loadAirport(redis)
        if not status[0]:
            return status

        status = self.loadCompanies(redis)
        if not status[0]:
            return status

        status = self.loadAirRoutes(redis)
        if not status[0]:
            return status

        status = self.loadEquipments(redis)
        if not status[0]:
            return status

        return [True, "AirportManager::loaded"]


    def init(self, airport):
        """
        When Airport Manager has loaded its resource,
        init() prepares resource allocation and monitoring.

        :param      airport:  Managed airport
        :type       airport:  MAnagedAirportBase
        """
        self.setRunways(airport.getRunways())
        self.setRamps(airport.getRamps())
        self.setEquipments(self.equipments)
        return [True, "AirportManager::inited"]


    def loadAirport(self, redis = None):
        """
        Loads an airport's data file and place its content in self.data
        """
        if redis is not None:
            k = key_path(REDIS_PREFIX.AIRPORT.value, "managed")
            self.data = rejson(redis=redis, key=k, db=REDIS_DB.REF.value)
            logger.debug(f"{k} loaded")
            return (True, "AirportManager::loadFromFile: loaded")
        else:
            business = os.path.join(MANAGED_AIRPORT_DIR, "airport.yaml")
            if os.path.exists(business):
                with open(business, "r") as fp:
                    self.data = yaml.safe_load(fp)
                logger.debug(f"{business} loaded")
                return (True, "AirportManager::loadFromFile: loaded")
        logger.warning(f"{business} not found")
        return (False, "AirportManager::loadFromFile file %s not found", business)


    def loadAirRoutes(self, redis = None):
        """
        Loads this airport's air routes from a data file.
        """
        if redis is not None:
            rkeys = rejson_keys(redis, key_path(REDIS_PREFIX.AIRLINE_ROUTES.value, "*"), db=REDIS_DB.REF.value)
            for key in rkeys:
                k = key.decode("UTF-8").split(ID_SEP)
                if len(k) == 5:
                    airline = Airline.findIATA(k[-2], redis)
                    if airline is not None:
                        if airline.icao not in self.airlines.keys():
                            self.airlines[airline.icao] = airline
                        airport = Airport.findIATA(k[-1], redis)
                        if airport is not None:
                            airline.addRoute(airport)
                            airport.addAirline(airline)
                        else:
                            logger.warning(f"airport {k[-1]} not found")
                    else:
                        logger.warning(f"airline {k[-2]} not found")
            logger.debug("loaded (Redis)")
        else:
            routes = os.path.join(MANAGED_AIRPORT_DIR, "airlines", "airline-routes.csv")
            file = open(routes, "r")
            csvdata = csv.DictReader(file)  # AIRLINE CODE,AIRPORT
            cnt = 0
            for row in csvdata:
                airline = Airline.findIATA(row["AIRLINE CODE"])
                if airline is not None:
                    if airline.icao not in self.airlines.keys():
                        self.airlines[airline.icao] = airline
                    airport = Airport.findIATA(row["AIRPORT"])
                    if airport is not None:
                        airline.addRoute(airport)
                        airport.addAirline(airline)
                        cnt = cnt + 1
                    else:
                        logger.warning(f"airport {row['AIRPORT']} not found")
                else:
                    logger.warning(f"airline {row['AIRLINE CODE']} not found")
            file.close()
            logger.debug("loaded %d airline routes for %d airlines" % (cnt, len(self.airlines)))

            fn = os.path.join(MANAGED_AIRPORT_DIR, "airlines", "airline-frequencies.csv")
            if os.path.exists(fn):
                self.airline_frequencies = {}
                with open(fn, "r") as file:
                    data = csv.DictReader(file)  # AIRLINE CODE,AIRPORT
                    for row in data:
                        self.airline_frequencies[row["AIRLINE CODE"]] = int(row["COUNT"])
                    logger.debug("airline-frequencies loaded")

            fn = os.path.join(MANAGED_AIRPORT_DIR, "airlines", "airline-route-frequencies.csv")
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
                    logger.debug("airline-route-frequencies loaded")
            logger.debug("loaded")

        return [True, "AirportManager::loadAirRoutes: loaded"]


    def getAirrouteCombo(self, airline = None, airport = None, redis = None):
        """
        Builds a list of (code, description) pairs for all routes for the airline operating at this airport.
        """
        if redis is not None:
            if airport is not None:
                key = key_path(REDIS_PREFIX.AIRPORT_ROUTES.value, airport)
                alns = rejson(redis=redis, key=key, db=REDIS_DB.REF.value)
                arr = []
                for aln in alns:
                    airline = Airline.findIATA(aln, redis)
                    arr.append((airline.iata, airline.orgId))
                return arr

            if airline is not None:
                key = key_path(REDIS_PREFIX.AIRLINE_ROUTES.value, airline)
                apts = rejson(redis=redis, key=key, db=REDIS_DB.REF.value)
                arr = []
                for apt in apts:
                    airport = Airport.findIATA(apt, redis)
                    arr.append((airport.iata, airport["properties"]["name"]))
                return arr

            logger.warning(f"no airline and no airport")
            return []

        routes = set()
        if airline is None:
            for al in self.airline_route_frequencies.values():
                ap = al.keys()
                if airport is None or airport in ap:
                    routes = routes.union(ap)
        else:
            routes = set(self.airline_route_frequencies[airline].keys())
        # return routes
        apts = list(filter(lambda a: a.iata in routes, Airport._DB_IATA.values()))
        return [(a.iata, a.display_name) for a in sorted(apts, key=py_operator.attrgetter('display_name'))]


    def selectRandomAirline(self):
        """
        Selects a random airline operating at this airport.
        """
        aln = None
        if self.airline_frequencies is not None:
            a = a = random.choices(population=list(self.airline_frequencies.keys()), weights=list(self.airline_frequencies.values()))
            aln = Airline.findIATA(a[0])
            if aln is not None:
                logger.debug(f"with density: {aln.icao}({aln.iata})")
            else:
                logger.warning(f"with density: {a[0]} not found")
        else:
            a = random.choice(list(self.airlines.keys()))
            aln = Airline.find(a)
            logger.debug(f"{a}")
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
                logger.warning(f"with density: {a[0]} not found")
            else:
                logger.debug(f"with density: {apt.icao}({apt.iata})")
        else:
            a = random.choice(list(aln.routes.keys()))
            apt = Airport.find(a)
            logger.debug(f"{a}")
        return (aln, apt)

    def hub(self, airport, airline):
        """
        Defines that an airline is using this airport as a hub.
        """
        airport.addHub(airline)
        airline.addHub(airport)


    def loadCompanies(self, redis = None):
        """
        Loads companies.

        :returns:   { description_of_the_return_value }
        :rtype:     { return_type_description }
        """
        if redis is not None:
            rkeys = rejson_keys(redis, key_path(REDIS_PREFIX.COMPANIES.value, "*"), db=REDIS_DB.REF.value)
            for key in rkeys:
                c = rejson(redis=redis, key=key, db=REDIS_DB.REF.value)
                if c is not None:
                    k = key.decode("UTF-8").split(ID_SEP)
                    self.companies[k[-1]] =Company(orgId=c["orgId"],
                                                   classId=c["classId"],
                                                   typeId=c["typeId"],
                                                   name=c["name"])
                else:
                    logger.warning(f"not found {key}")
            logger.debug("loaded (Redis)")
            return (True, f"AirportManager::loadCompanies loaded")
        else:
            companies = os.path.join(MANAGED_AIRPORT_DIR, "services", "companies.yaml")
            if os.path.exists(companies):
                with open(companies, "r") as fp:
                    self.data = yaml.safe_load(fp)
                logger.warning(f"{companies} loaded")
                for k, c in self.data.items():
                    self.companies[k] = Company(orgId=c["orgId"],
                                                classId=c["classId"],
                                                typeId=c["typeId"],
                                                name=c["name"])
                return (True, f"AirportManager::loadCompanies loaded {self.companies.keys()}")
        return (False, f"AirportManager::loadCompanies not loaded")


    def getCompany(self, company):
        return self.companies[company] if company in self.companies else None


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
        return list([(c.orgId, c.name) for c in companies])


    def loadEquipments(self, redis = None):
        """
        Loads equipment fleet and creates vehicle.
        """
        if redis is not None:
            vehicles = rejson_keys(redis, key_path(REDIS_PREFIX.GSE.value, "*"), db=REDIS_DB.REF.value)
            servicevehicleclasses = importlib.import_module(name=".service.equipment", package="emitpy")
            for v in vehicles:
                vdat = rejson(redis=redis, key=v, db=REDIS_DB.REF.value)
                vname = vdat["registration"]
                model = vdat["model"].replace("-", "_")  # now model is snake_case
                mdl = ''.join(word.title() for word in model.split('_'))  # now model is CamelCase
                vcl = vdat["service"].title() + "Vehicle" + mdl
                if hasattr(servicevehicleclasses, vcl):
                    # @todo: shoudl reconstruct Company from data
                    vehicle = getattr(servicevehicleclasses, vcl)(registration=vname, operator=self.operator)  ## getattr(sys.modules[__name__], str) if same module...
                    vehicle.setICAO24(vdat["icao24"])  # starts with F like fleet.
                    self.equipments[vname] = vehicle
                    if vcl not in self.equipment_by_type:
                        self.equipment_by_type[vcl] = []
                    self.equipment_by_type[vcl].append(vehicle)
                    # logger.debug(f"..added {vname}")
                else:
                    logger.debug(f"vehicle type {vcl} not found")
            # self.setEquipments(self.equipments)
            logger.debug(f"..done")
            return (True, "AirportManager::loadEquipments: loaded")
        else:
            business = os.path.join(MANAGED_AIRPORT_DIR, "services", "equipment.yaml")
            if os.path.exists(business):
                with open(business, "r") as fp:
                    self.data = yaml.safe_load(fp)
                logger.debug(f"{business} loaded")
                servicevehicleclasses = importlib.import_module(name=".service.equipment", package="emitpy")
                #  type: fuel
                #  model: large-tanker
                #  flow: 40
                #  capacity: 34000
                #  fleet: 4
                for equipment in self.data["equipment"]:
                    vtyp = equipment.get(EQUIPMENT.TYPE.value)
                    vmod = equipment.get(EQUIPMENT.MODEL.value)
                    vqty = equipment.get(EQUIPMENT.COUNT.value, 1)
                    vcl = vtyp[0].upper() + vtyp[1:] + "Vehicle"
                    vname_root = vtyp
                    if vmod is not None:
                        vcl = vcl + KebabToCamel(vmod)
                        vname_root = vname_root + vmod.replace("-", "")
                    else:
                        vname_root = vname_root + DEFAULT_VEHICLE_SHORT

                    if hasattr(servicevehicleclasses, vcl):
                        for idx in range(int(vqty)):
                            vname = f"{vname_root}{idx:03d}"
                            vehicle = getattr(servicevehicleclasses, vcl)(registration=vname, operator=self.operator)  ## getattr(sys.modules[__name__], str) if same module...
                            icao24 = AirportManager.randomICAO24(15)
                            vehicle.setICAO24(icao24)  # starts with F like fleet.
                            # Set service props
                            vehicle.setProperties(equipment)
                            #
                            if vname in self.equipments:
                                logger.warning(f"{vname} already exists, overriding")
                            self.equipments[vname] = vehicle
                            if vcl not in self.equipment_by_type:
                                self.equipment_by_type[vcl] = []
                            self.equipment_by_type[vcl].append(vehicle)
                            # logger.debug(f"..added {vname} ({icao24})")
                    else:
                        logger.warning(f"vehicle type {vcl} not found")
                    # logger.debug(f"..{vtype} done")

                # self.setEquipments(self.equipments)
                logger.debug(f"..done")
                return (True, "AirportManager::loadEquipments: loaded")
            logger.warning(f"{business} not found")

        logger.warning(f"not loaded")
        return (False, "AirportManager::loadEquipments: not loaded")


    def selectEquipment(self, operator: "Company", service: "Service", reqtime: datetime, reqend: datetime = None,
                        model: str = None, registration: str = None, use: bool = True):  # quantity: float = None,
        """
        Selects a equipment for ground support.
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
        vehicle = None

        # If we have a registration, use that vehicle if it exists.
        if vname is not None and vname in self.equipments.keys():
            vehicle = self.equipments[vname]
            logger.debug(f"found existing {vehicle.registration}")
            if use: # there is no check that the vehicle is available  !!!!!!! @todo
                service.setVehicle(vehicle)
                if reqend is None:
                    reqend = reqtime + timedelta(seconds=service.duration())
                # @warning: We should book the vehicle before setting it for service.
                # However, service.getId() complains it has no vehicle set, we set the vehicle "first"
                # so that it appears nicely in the .getId() call. (and does not provoke a warning.)
                res = self.equipment_allocator.book(vehicle.getResourceId(), reqtime, reqend, service.getId())
                logger.debug(f"using {vehicle.registration} (**even if not available**)")
            return vehicle

        if vname is not None:
            logger.debug(f"requested vehicle {vname} not found")
        else:
            logger.debug(f"finding suitable vehicle for {type(service).__name__}..")

        # If not, we determine the type of vehicle we need
        svc_name = None
        vcl = None
        vcl_short = None
        if (type(service).__name__).__contains__("Service"):
            svc_name = (type(service).__name__).replace("Service", "")
            vcl = svc_name + "Vehicle"
            vcl_short = svc_name[0:3].upper()
        elif (type(service).__name__).__contains__("Mission"):
            svc_name = "Mission"
            vcl = "MissionVehicle"
            vcl_short = "MIS"
        else:
            logger.warning(f"invalid service {type(service).__name__}")

        logger.debug(f"service {svc_name}, base vehicle {vcl}, looking for model {model}")
        if model is None or model.endswith(DEFAULT_VEHICLE):  # is_default_model(model):
            vcl_short = vcl_short + DEFAULT_VEHICLE_SHORT  # Standard Vehicle
            logger.debug(f"standard model is {vcl}, {vcl_short}")
        else:
            # model = model.replace("-", "_")  # now model is snake_case (was kebab-case)
            mdl = ''.join(word.title() for word in model.split('-'))  # now model is CamelCase
            vcl = vcl + mdl
            vcl_short = vcl_short + mdl[0:2].upper()
            logger.debug(f"model {model} is {vcl}, {vcl_short}")

        logger.debug(f"service {svc_name}, use vehicle {vcl}: {vcl_short}, reg={vname}")
        servicevehicleclasses = importlib.import_module(name=".service.equipment", package="emitpy")

        # If we have a registration, but the vehicle instance does not exist, we need to create it.
        if vname is not None:
            if hasattr(servicevehicleclasses, vcl):
                logger.debug(f"creating new {vcl} with registration {vname}..")
                vehicle = getattr(servicevehicleclasses, vcl)(registration=vname, operator=operator)  ## getattr(sys.modules[__name__], str) if same module...
                vehicle.setICAO24(AirportManager.randomICAO24(10))  # starts with A
                self.equipments[vname] = vehicle
                if vcl not in self.equipment_by_type:
                    self.equipment_by_type[vcl] = []
                self.equipment_by_type[vcl].append(vehicle)
                #  need to add it to alloc table and book it
                self.equipment_allocator.add(vehicle)
                logger.debug(f"..created")
            else:
                logger.error(f"..not created. No vehicle type {vcl}.")
                return None

        # no registration, we can try to find any vehicle of requested type
        else:
            if vcl in self.equipment_by_type:
                logger.debug(f"trying to find a suitable {vcl}..")
                idx = 0
                vehicle = None
                res = None
                while vehicle is None and idx < len(self.equipment_by_type[vcl]):
                    v = self.equipment_by_type[vcl][idx]
                    if self.equipment_allocator.isAvailable(v.getResourceId(), reqtime, reqend):
                        vehicle = v
                        logger.debug(f"..found: reusing {vcl} {vehicle.registration}..")
                    idx = idx + 1

            if vehicle is None:
                logger.debug(f"..no vehicle of type {vcl} available. Adding one..")  # !! infinite resources !!
                vname = f"{vcl_short}{self.equipment_number:03d}"
                self.equipment_number = self.equipment_number + 1
                # create vehicle
                if hasattr(servicevehicleclasses, vcl):
                    logger.debug(f"creating {vname} {vcl}..")
                    vehicle = getattr(servicevehicleclasses, vcl)(registration=vname, operator=operator)  ## getattr(sys.modules[__name__], str) if same module...
                    vehicle.setICAO24(AirportManager.randomICAO24(10))  # starts with A
                    self.equipments[vname] = vehicle
                    if vcl not in self.equipment_by_type:
                        self.equipment_by_type[vcl] = []
                    self.equipment_by_type[vcl].append(vehicle)
                    #  need to add it to alloc table and book it
                    self.equipment_allocator.add(vehicle)
                    logger.debug(f"..added")
                else:
                    logger.error(f"..not created. No vehicle type {vcl}.")
                    return None

        # If we have a vehicle, book it if requested, and returned it
        if vehicle is not None:
            if use:
                service.setVehicle(vehicle)
                if reqend is None:
                    reqend = reqtime + timedelta(seconds=service.duration())
                # @warning: We should book the vehicle before setting it for service.
                # However, service.getId() complains it has no vehicle set, we set the vehicle "first"
                # so that it appears nicely in the .getId() call. (and does not provoke a warning.)
                res = self.equipment_allocator.book(vehicle.getResourceId(), reqtime, reqend, service.getId())
                vehicle.addAllocation(res)
                logger.debug(f"vehicle booked {vehicle.getResourceId()} for {service.getId()}")
            else:
                logger.debug(f"found vehicle {vehicle.getResourceId()} but not used")
            return vehicle

        logger.warning(f"returning no vehicle {vcl} for {service.getId()}")
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
            r = ""
            while len(r) < 6:  # prevent icao with less than 6 hexadecimal digit
                r = f"{root:x}{random.getrandbits(20):x}"
            return r

        r = ""
        while len(r) < 6:  # prevent icao with less than 6 hexadecimal digit
            r = f"{random.getrandbits(24):x}"
        return r


    def setEquipments(self, vehicles):
        self.equipments = vehicles
        logger.debug(f"allocating..")
        self.equipment_allocator = AllocationTable(resources=self.equipments.values(),
                                                   name="equipment")
        logger.info(f"resources added: {len(self.equipment_allocator.resources.keys())}")
        logger.debug(f"..done")


    def bookVehicle(self, vehicle: "Equipment", reqtime: "datetime", reqduration: int, reason: str):
        reqend = reqtime + timedelta(minutes=reqduration)
        avail = self.equipment_allocator.isAvailable(vehicle.getResourceId(), reqtime, reqend)
        if avail:
            self.equipment_allocator.book(vehicle.getResourceId(), reqtime, reqend, reason)
        return avail


    def setRamps(self, ramps):
        self.ramps = ramps
        logger.debug(f"allocating..")
        self.ramp_allocator = AllocationTable(resources=self.ramps.values(),
                                              name="ramps")
        logger.info(f"resources added: {len(self.ramp_allocator.resources.keys())}")
        logger.debug(f"..done")


    def bookRamp(self, ramp: "Ramp", reqtime: "datetime", reqduration: int, reason: str):
        reqend = reqtime + timedelta(minutes=reqduration)
        avail = self.ramp_allocator.isAvailable(ramp.getResourceId(), reqtime, reqend)
        if avail:
            self.ramp_allocator.book(ramp.getResourceId(), reqtime, reqend, reason)
        return avail


    def setRunways(self, runways):
        self.runways = runways
        logger.debug(f"allocating..")
        self.runway_allocator = AllocationTable(resources=[], name="runways")
        for rwy in self.runways.values():
            rwy_id = rwy.getResourceId()
            if rwy_id not in self.runway_allocator.resources.keys():
                self.runway_allocator.createNamedResource(rwy, rwy_id)
        logger.info(f"resources added: {self.runway_allocator.resources.keys()}")
        logger.debug(f"..done")


    def bookRunway(self, runway: "Runway", reqtime: "datetime", reqduration: int, reason: str):
        reqend = reqtime + timedelta(minutes=reqduration)
        avail = self.runway_allocator.isAvailable(runway.getResourceId(), reqtime, reqend)
        if avail:
            self.runway_allocator.book(runway.getResourceId(), reqtime, reqend, reason)
        return avail

    def saveAllocators(self, redis):
        self.equipment_allocator.save(redis)
        self.ramp_allocator.save(redis)
        self.runway_allocator.save(redis)

    def loadAllocators(self, redis):
        self.runway_allocator.load(redis)
        self.ramp_allocator.load(redis)
        self.equipment_allocator.load(redis)

    def checkAllocators(self, redis):
        logger.info(f"runways: {len(self.runway_allocator.resources.keys())}")
        logger.info(f"ramps: {len(self.ramp_allocator.resources.keys())}")
        logger.info(f"vehicles: {len(self.equipment_allocator.resources.keys())}")

    def allFlights(self, redis):
        keys = redis.keys(key_path(REDIS_DATABASE.FLIGHTS.value, "*", REDIS_TYPE.EMIT_META.value))
        items = []
        if items is not None and len(keys) > 0:
            for f in keys:
                items.append(ID_SEP.join(f.decode("UTF-8").split(ID_SEP)[:-1]))
            return set(items)
        return items


    def allMissions(self, redis):
        keys = redis.keys(key_path(REDIS_DATABASE.MISSIONS.value, "*", REDIS_TYPE.EMIT_META.value))
        items = []
        if keys is not None and len(keys) > 0:
            for f in keys:
                items.append(ID_SEP.join(f.decode("UTF-8").split(ID_SEP)[:-1]))
            return set(items)
        return items


    def allServicesForFlight(self, redis, flight_id: str, redis_type=REDIS_TYPE.EMIT_META.value):
        emit = ReEmit(flight_id, redis)
        emit_meta = emit.getMeta()

        # 1. Try with collection of services
        fid = emit.getMeta("$.move.flight.identifier")
        if fid is not None:
            ret = []
            base = key_path(REDIS_DATABASE.FLIGHTS.value, fid, REDIS_DATABASE.SERVICES.value)
            services = redis.smembers(base)
            if services is not None:
                logger.debug(f"found {len(services)} services for {fid}")
                for sid in services:
                    sid = sid.decode("UTF-8")
                    sarr = sid.split(ID_SEP)
                    if sarr[0] != EVENT_ONLY_SERVICE:  # regular move, this collects all the emits
                        skey = key_path(REDIS_DATABASE.SERVICES.value, sid, "*", redis_type)
                        pkeys = redis.keys(skey)
                        if pkeys is not None:
                            pkeys2 = [k.decode("UTF-8") for k in pkeys]
                            ret = ret + pkeys2
                            logger.debug(f"found {pkeys2}")
                    else:
                        logger.debug(f"found event service {sid}, ignoring emit, will recreate message")
                if len(ret) == 0:
                    logger.debug(f"{fid} has no service with vehicle")
                return ret
            else:
                logger.debug(f"{fid} has no service associated, trying select")
        else:
            logger.debug(f"no {fid}, trying select")

        # 2. Try by scheduled times and ramp
        items = []
        is_arrival = emit.getMeta("$.move.flight.is_arrival")
        if is_arrival is None:
            logger.warning(f"cannot get flight movement")
            return ()

        before = None
        if is_arrival:
            before = 60
            after = 180
        else:
            before = 180
            after = 60

        scheduled = emit.getMeta("$.move.scheduled")
        if scheduled is None:
            logger.warning(f"cannot get flight scheduled time {emit.getMeta()}")
            return ()
        scheduled = datetime.fromisoformat(scheduled)

        et_min = scheduled - timedelta(minutes=before)
        et_max = scheduled + timedelta(minutes=after)
        logger.debug(f"{ARRIVAL if is_arrival else DEPARTURE} at {scheduled}")
        logger.debug(f"trying services between {et_min} and {et_max}")

        # 2 search for all services at that ramp, "around" supplied ETA/ETD.
        ramp = emit.getMeta("$.move.ramp.name")
        keys = redis.keys(key_path(REDIS_DATABASE.SERVICES.value, "*", ramp, "*", redis_type))
        for k in keys:
            k = k.decode("UTF-8")
            karr = k.split(ID_SEP)
            sid = karr[1:]  # remove database name
            sarr = sid.split(ID_SEP)
            if sarr[0] != EVENT_ONLY_SERVICE:  # regular move, this collects all the emits
                dt = datetime.strptime(sarr[2], FLIGHT_TIME_FORMAT).replace(tzinfo=timezone.utc)
                logger.debug(f"{k}: testing {dt}..")
                if dt > et_min and dt < et_max:
                    items.append(k)
                    logger.debug(f"added {k}..")
            else:
                logger.debug(f"found event service {sid}, ignoring emit, will recreate message")
        logger.debug(f"..done")
        return set(items)


    def allServiceOfType(self, redis, service_type: str):
        service_class = service_type[0].upper() + service_type[1:].lower() + "Service"  # @todo: Hum.
        ks = key_path(REDIS_DATABASE.SERVICES.value, service_class, "*", REDIS_TYPE.EMIT_META.value)
        # logger.debug(f"trying {ks}")
        keys = redis.keys(ks)
        items = []
        if keys is not None and len(keys) > 0:
            for f in keys:
                items.append(ID_SEP.join(f.decode("UTF-8").split(ID_SEP)[:-1]))
            return set(items)
        return items


    def allServiceForRamp(self, redis, ramp_id: str):
        ks = key_path(REDIS_DATABASE.SERVICES.value, "*", ramp_id, "*", REDIS_TYPE.EMIT_META.value)
        logger.debug(f"trying {ks}")
        keys = redis.keys(ks)
        items = []
        if keys is not None and len(keys) > 0:
            for f in keys:
                items.append(ID_SEP.join(f.decode("UTF-8").split(ID_SEP)[:-1]))
            return set(items)
        return items


    def addAircraft(self, aircraft):
        self.flights[aircraft.getId()] = aircraft

    def updateAircraft(self, aircraft):
        self.flights[aircraft.getId()] = aircraft

    def getAircrafts(self):
        return self.aircrafts

    def addFlight(self, flight):
        self.flights[flight.getId()] = flight

    def updateFlight(self, flight):
        self.flights[flight.getId()] = flight

    def getFlights(self):
        return self.flights

    def getTurnaroundProfile(self, flight, redis):
        """
        Loads a turnaround profile data file from turnaround characteristics (should pass entire flight).
        """
        # C-cargo-arrival-tiedown
        ac_class = flight.aircraft.actype.getClass()
        is_cargo = flight.is_cargo()
        is_arrival = flight.is_arrival()
        is_jetway = flight.has_jetway()

        tar_profile = None
        profile_name = ac_class
        class_pos = len(profile_name) - 1
        _STD_CLASS = "C"  # from emitpy.aircraft import _STD_CLASS

        if is_cargo:
            profile_name = profile_name + "-cargo"
        else:
            profile_name = profile_name + "-pax"

        if is_arrival:
            profile_name = profile_name + "-arrival"
        else:
            profile_name = profile_name + "-departure"

        if is_jetway:
            profile_name = profile_name + "-jetway"
        else:
            profile_name = profile_name + "-tiedown"

        logger.debug(f"selected {profile_name}")

        if redis:
            key = key_path(REDIS_PREFIX.TAR_PROFILES.value, profile_name.replace("-", ":"))
            tar_profile = rejson(redis=redis, key=key, db=REDIS_DB.REF.value)
            if tar_profile is None:
                logger.debug(f"{profile_name} does not exist, trying default..")
                profile_name = list(profile_name)
                profile_name[class_pos] = _STD_CLASS
                profile_name = ''.join(profile_name)  # https://stackoverflow.com/questions/10631473/str-object-does-not-support-item-assignment
                key = key_path(REDIS_PREFIX.TAR_PROFILES.value, profile_name.replace("-", ":"))
                tar_profile = rejson(redis=redis, key=key, db=REDIS_DB.REF.value)
                if tar_profile is None:
                    logger.error(f"..standard {profile_name} not found ({key})")
        else:  # no redis
            dirname = os.path.join(MANAGED_AIRPORT_DIR, "services", "ta-profiles")
            filename = os.path.join(dirname, profile_name + ".yaml")
            if os.path.exists(filename):
                with open(filename, "r") as fp:
                    tar_profile = yaml.safe_load(fp)
                    logger.debug(f"{profile_name} loaded")
            else:
                logger.debug(f"{profile_name} does not exist, trying default..")
                profile_name = list(profile_name)
                profile_name[class_pos] = _STD_CLASS
                profile_name = ''.join(profile_name)  # https://stackoverflow.com/questions/10631473/str-object-does-not-support-item-assignment
                filename = os.path.join(dirname, profile_name + ".yaml")
                if os.path.exists(filename):
                    with open(filename, "r") as fp:
                        tar_profile = yaml.safe_load(fp)
                        logger.debug(f"..standard {profile_name} loaded")
                else:
                    logger.error(f"..standard {profile_name} not found ({filename})")

        return tar_profile
