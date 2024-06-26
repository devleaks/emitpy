import os
import sys

from networkx import convert

# from parameters import HOME_DIR
sys.path.append(os.path.join(".."))  # os.path.join(HOME_DIR, "src"), changed to avoid dependancy on parameter

import logging
import json
import yaml
import time

import redis
from redis.commands.json.path import Path
from fastapi.encoders import jsonable_encoder

from datetime import datetime

import emitpy
from emitpy.managedairport import ManagedAirport
from emitpy.business import Airline, AirportManager
from emitpy.aircraft import AircraftType, AircraftTypeWithPerformance
from emitpy.airspace import NamedPoint, NavAid, CPIDENT, AirwaySegment, Terminal, ControlledAirspace, XPAerospace
from emitpy.airport import Airport, XPAirport
from emitpy.weather import WebWeatherEngine

from emitpy.constants import REDIS_DB, REDIS_DATABASE, REDIS_PREFIX, REDIS_LOVS, POI_COMBO, key_path, AIRAC_CYCLE
from emitpy.constants import MANAGED_AIRPORT_KEY, MANAGED_AIRPORT_LAST_UPDATED, AIRCRAFT_TYPE_DATABASE, FLIGHTROUTE_DATABASE

from emitpy.parameters import REDIS_CONNECT, REDIS_ATTEMPTS, REDIS_WAIT
from emitpy.parameters import MANAGED_AIRPORT_ICAO, DATA_DIR, MANAGED_AIRPORT_DIR
from emitpy.geo import FeatureWithProps


logger = logging.getLogger("LoadApp")

logging.basicConfig(level=logging.DEBUG)


class LoadApp(ManagedAirport):
    def __init__(self, icao: str, data_to_load: list = ["*"]):
        self._use_redis = False

        self._aerospace = XPAerospace
        self._managedairport = XPAirport
        self._airportmanager = AirportManager
        self._weather_engine = WebWeatherEngine  # XPWeatherEngine

        ManagedAirport.__init__(self, icao=icao, app=self)

        self.redis_pool = None
        self.redis = None

        ret = self.init(
            load_airways=(data_to_load is None or "*" in data_to_load or "airway" in data_to_load)
        )  # call init() here to use data from data files (no Redis supplied)
        if not ret[0]:
            logger.warning(ret[1])

        # Redis available from now on
        self.redis_pool = redis.ConnectionPool(**REDIS_CONNECT)
        self.redis = redis.Redis(connection_pool=self.redis_pool)
        try:
            pong = self.redis.ping()
        except redis.RedisError:
            logger.error("cannot connect to redis")
            return

        # All reference data stored in REDIS_DB.REF
        prevdb = self.redis.client_info()["db"]
        self._app.redis.select(REDIS_DB.REF.value)

        logger.debug("=" * 90)
        logger.debug("initialized. ready to save. saving..")

        # Caching emitpy lists of values Redis
        # We need to cache lov first because we will reset
        # some collections and loose some data/links
        self.cache_lovs()

        # Caching emitpy data into Redis
        status = self.load(data_to_load)
        if not status[0]:
            logger.error(f"{status[1]}")
            logger.error("..NOT DONE")
            logger.debug("NOT COMPLETED SUCCESSFULLY")
        else:
            logger.debug("..saved")
            logger.debug("completed successfully")

        logger.debug("=" * 90)

        # Restore default db
        self._app.redis.select(prevdb)

    @staticmethod
    def is_loaded(redis):
        """
        Determines whether emitpy data is loaded in Redis.
        Returns (True|False, comment), where comment is datetime of last load
        :param      redis:  The redis
        :type       redis:  { type_description }
        """
        prevdb = redis.client_info()["db"]
        redis.select(REDIS_DB.REF.value)
        k = key_path(REDIS_PREFIX.AIRPORT.value, MANAGED_AIRPORT_KEY)
        a = redis.json().get(k, Path.root_path())
        redis.select(prevdb)
        if a is not None and MANAGED_AIRPORT_LAST_UPDATED in a:
            return (True, a[MANAGED_AIRPORT_LAST_UPDATED])
        return (False, f"{k} not found")

    def use_redis(self):
        return None

    def load(self, what: list):
        logger.debug(f"loading.. ({what})")

        # #############################
        # GENERIC
        #
        if "*" in what or "actype" in what:
            status = self.loadAircraftTypes()
            if not status[0]:
                return status
            else:
                logger.info(f"{status[1]}")

        if "*" in what or "acperf" in what:
            status = self.loadAircraftPerformances()
            if not status[0]:
                return status
            else:
                logger.info(f"{status[1]}")

        if "*" in what or "acequiv" in what:
            status = self.loadAircraftEquivalences()
            if not status[0]:
                return status
            else:
                logger.info(f"{status[1]}")

        if "*" in what or "actaprof" in what:
            status = self.loadTurnaroundProfiles()
            if not status[0]:
                return status
            else:
                logger.info(f"{status[1]}")

        if "*" in what or "airport" in what:
            status = self.loadAirports()
            if not status[0]:
                return status
            else:
                logger.info(f"{status[1]}")

        if "*" in what or "airline" in what:
            status = self.loadAirlines()
            if not status[0]:
                return status
            else:
                logger.info(f"{status[1]}")

        if "*" in what or "airroute" in what:
            status = self.loadAirRoutes()
            if not status[0]:
                return status
            else:
                logger.info(f"{status[1]}")

        # #############################
        # AIRSPACE
        #
        # it is no longer necessary to load airspace in Redis, it is pickle cached (faster)
        # if "*" in what or "vertex" in what:
        #     status = self.loadVertices()
        #     if not status[0]:
        #         return status

        # if "apt" in what:
        #     status = self.loadTerminals()
        #     if not status[0]:
        #         return status

        # if "navaid" in what:
        #     status = self.loadNavaids()
        #     if not status[0]:
        #         return status

        # if "fix" in what:
        #     status = self.loadFixes()
        #     if not status[0]:
        #         return status

        # if "*" in what or "hold" in what:
        #     status = self.loadHolds()
        #     if not status[0]:
        #         return status

        # if "*" in what or "airway" in what:
        #     status = self.loadAirways()
        #     if not status[0]:
        #         return status

        if "*" in what or "airspace" in what:
            status = self.loadAirspaces()
            if not status[0]:
                return status

        # #############################
        # AIRPORT MANAGER
        #
        if "*" in what or "alfreq" in what:
            status = self.loadAirlineFrequencies()
            if not status[0]:
                return status
            else:
                logger.info(f"{status[1]}")

        if "*" in what or "alroute" in what:
            status = self.loadAirlineRoutes()
            if not status[0]:
                return status
            else:
                logger.info(f"{status[1]}")

        if "*" in what or "alroutefreq" in what:
            status = self.loadAirlineRouteFrequencies()
            if not status[0]:
                return status
            else:
                logger.info(f"{status[1]}")

        if "*" in what or "comp" in what:
            status = self.loadCompanies()
            if not status[0]:
                return status
            else:
                logger.info(f"{status[1]}")

        if "*" in what or "gse" in what:
            status = self.loadGSE()
            if not status[0]:
                return status
            else:
                logger.info(f"{status[1]}")

        if "*" in what or "gsefleet" in what:
            status = self.loadGSEFleet()
            if not status[0]:
                return status
            else:
                logger.info(f"{status[1]}")

        # #############################
        # MANAGED AIRPORT
        #

        # it no longer is necessary to load flight plans/routes
        # if "*" in what or "fpdb" in what:
        #     status = self.loadFlightPlans()
        #     if not status[0]:
        #         return status

        if "*" in what or "ramp" in what:
            status = self.loadRamps()
            if not status[0]:
                return status
            else:
                logger.info(f"{status[1]}")

        if "*" in what or "rwy" in what:
            status = self.loadRunways()
            if not status[0]:
                return status
            else:
                logger.info(f"{status[1]}")

        if "*" in what or "apoi" in what:
            status = self.loadAirwayPOIS()
            if not status[0]:
                return status
            else:
                logger.info(f"{status[1]}")

        if "*" in what or "spoi" in what:
            status = self.loadServicePOIS()
            if not status[0]:
                return status
            else:
                logger.info(f"{status[1]}")

        # if "*" in what or "dpoi" in what:
        #     status = self.loadServiceDestinations()
        #     if not status[0]:
        #         return status
        #     else:
        #         logger.info(f"{status[1]}")

        if "*" in what or "cpoi" in what:
            status = self.loadCheckpoints()
            if not status[0]:
                return status
            else:
                logger.info(f"{status[1]}")

        # it no longer is necessary to load graphs, they are pickled
        # if "taxiways" in what:
        #     status = self.loadGraph("taxiways", self.airport.taxiways)
        #     if not status[0]:
        #         return status

        # it no longer is necessary to load graphs, they are pickled
        # if "serviceroads" in what:
        #     status = self.loadGraph("serviceroads", self.airport.service_roads)
        #     if not status[0]:
        #         return status
        if "*" in what or "info" in what:
            try:
                info = self.getAirportDetails()
                if info is None:
                    logger.warning(f"LoadApp::load: not loaded info, info not found")
                    return (False, f"LoadApp::load: info NOT loaded")

                key = key_path(REDIS_PREFIX.AIRPORT.value, MANAGED_AIRPORT_KEY)
                old = r.json().get(key)
                action = "loaded"
                if a is not None and MANAGED_AIRPORT_LAST_UPDATED in a:
                    action = "updated"
                if self.airport.airspace is not None:
                    info[AIRAC_CYCLE] = self.airport.airspace.getAiracCycle()
                else:
                    logger.warning(f"LoadApp::load: AIRAC cycle not saved")
                info[MANAGED_AIRPORT_LAST_UPDATED] = datetime.now().astimezone().isoformat()
                self.redis.json().set(key, Path.root_path(), info)
                logger.info(f"LoadApp::load: {action} info (key {key})")
            except:
                logger.warning(f"LoadApp::load: not loaded info", exc_info=True)
                return (False, f"LoadApp::load: info NOT loaded")

        logger.debug(f"..loaded")
        return (True, f"LoadApp::load: loaded")

    # ####################################################################################################################
    #
    #
    # #############################
    # GENERIC
    #
    def loadAircraftTypes(self):
        if len(AircraftType._DB) == 0:
            AircraftType.loadAll()
        for a in AircraftType._DB.values():
            a.save(REDIS_PREFIX.AIRCRAFT_TYPES.value, self.redis)
        logger.debug(f"loaded {len(AircraftType._DB)} aircraft types")
        return (True, f"LoadApp::loadAircraftTypes: loaded aircraft types")

    def loadAircraftPerformances(self):
        if len(AircraftType._DB) == 0:
            AircraftType.loadAll()
        if len(AircraftTypeWithPerformance._DB_PERF) == 0:
            AircraftTypeWithPerformance.loadAll()
        for a in AircraftTypeWithPerformance._DB_PERF.values():
            a.save(REDIS_PREFIX.AIRCRAFT_PERFS.value, self.redis)

        def saveid(k):
            AircraftTypeWithPerformance._DB_PERF[k].save_id = k
            return AircraftTypeWithPerformance._DB_PERF[k]

        g1 = map(saveid, AircraftTypeWithPerformance._DB_PERF.keys())
        g2 = filter(lambda a: a.check_availability(), g1)
        gdict = dict([(v.save_id, v.getInfo()) for v in g2])
        self.redis.json().set(REDIS_PREFIX.AIRCRAFT_PERFS.value, Path.root_path(), gdict)
        # a = list(gdict.values())
        # self.redis.json().set(REDIS_PREFIX.AIRCRAFT_PERFS.value + "2", Path.root_path(), a)

        logger.debug(f"loaded {len(gdict)}/{len(AircraftTypeWithPerformance._DB_PERF)} aircraft performances")
        return (True, f"LoadApp::loadAircraftPerformances: loaded aircraft performances")

    def loadAircraftEquivalences(self):
        if len(AircraftType._DB) == 0:
            AircraftType.loadAll()
        if len(AircraftTypeWithPerformance._DB_PERF) == 0:
            AircraftTypeWithPerformance.loadAll()
        EQUIVALENCES = "equivalences"
        cnt = 0
        for k, v in AircraftTypeWithPerformance._DB_PERF.items():
            if EQUIVALENCES in v.perfraw.keys():
                equivs = v.perfraw[EQUIVALENCES]
                self.redis.sadd(key_path(REDIS_PREFIX.AIRCRAFT_EQUIS.value, k), *equivs)
                cnt = cnt + 1
                # Add reverse equivalence
                for v1 in equivs:
                    cnt = cnt + 1
                    self.redis.sadd(key_path(REDIS_PREFIX.AIRCRAFT_EQUIS.value, v1), k)
        logger.debug(f"loaded {cnt} aircraft equivalences")
        return (True, f"LoadApp::loadAircraftEquivalences: loaded aircraft equivalences")

    def loadTurnaroundProfiles(self):
        def loadFromFile(fn):
            filename = os.path.join(DATA_DIR, AIRCRAFT_TYPE_DATABASE, fn)
            data = None
            if os.path.exists(filename):
                # logger.debug(f"loadFromFile {filename}..")
                with open(filename, "r") as file:
                    if filename[-5:] == ".yaml":
                        data = yaml.safe_load(file)
                    else:  # JSON or GeoJSON
                        data = json.load(file)
                # logger.debug(f"loadFromFile {filename} .. loaded")
                return data
            else:
                logger.warning(f"file not found {filename}")
            return None

        for actype in "ABCDEF":  # one day, we'll loop over each ac type...
            #
            # RAMP Service Vehicle Positions around aircraft
            gseprofile = loadFromFile(f"{actype}-gseprf.yaml")
            if gseprofile is not None:
                self.redis.json().set(key_path(REDIS_PREFIX.AIRCRAFT_GSEPROFILES.value, actype), Path.root_path(), gseprofile)
                logger.debug(f"loaded GSE profile for aircraft class {actype}")
            else:
                logger.debug(f"no GSE profile for aircraft class {actype}")

        #
        # Turnaround Profiles
        dirname = os.path.join(MANAGED_AIRPORT_DIR, "services", "ta-profiles")
        for f in os.listdir(dirname):
            if not f.startswith(".") and f.endswith(".yaml"):
                tarname = f.replace(".yaml", "")
                key = key_path(REDIS_PREFIX.TAR_PROFILES.value, tarname.replace("-", ":"))
                tarprofile = loadFromFile(os.path.join(dirname, f))
                if tarprofile is not None:
                    self.redis.json().set(key, Path.root_path(), tarprofile)
                    logger.debug(f"loaded turnaround profile for {tarname}")
                else:
                    logger.debug(f"no turnaround profile for {tarname}")

        return (True, f"LoadApp::loadTurnaroundProfiles: loaded turnaround profile for aircraft classes")

    def loadAirports(self):
        def packapt(a):
            r = a.to_geojson()
            r["properties"]["_info"] = a.getInfo()
            return r

        if len(Airport._DB) == 0:
            Airport.loadAll()

        for v in Airport._DB.values():  # Airline does not serialize
            v.airlines = [(a.iata, a.orgId) for a in v.airlines.values()]

        errcnt = 0
        for a in Airport._DB.values():
            a.save(key_path(REDIS_PREFIX.AIRPORTS.value, REDIS_PREFIX.ICAO.value), self.redis)
            try:  # we noticed, experimentally, abs(lon) > 85 is not good...
                self.redis.geoadd(REDIS_PREFIX.AIRPORTS_GEO_INDEX.value, (a.lon(), a.lat(), a.icao))
            except:
                logger.debug(f"cannot load {a.icao} (lat={a.lat()}, lon={a.lon()})")
                errcnt = errcnt + 1
        self.redis.json().set(key_path(REDIS_PREFIX.AIRPORTS.value, REDIS_PREFIX.ICAO.value), Path.root_path(), {k: packapt(a) for k, a in Airport._DB.items()})
        self.redis.json().set(
            key_path(REDIS_PREFIX.AIRPORTS.value, REDIS_PREFIX.IATA.value), Path.root_path(), {k: packapt(a) for k, a in Airport._DB_IATA.items()}
        )
        logger.debug(f"loaded {len(Airport._DB)} airports ({errcnt} geo errors)")
        return (True, f"LoadApp::loadAirports: loaded airports")

    def loadAirlines(self):
        if len(Airline._DB) == 0:
            Airline.loadAll()
        for a in Airline._DB.values():
            a.save(key_path(REDIS_PREFIX.AIRLINES.value, REDIS_PREFIX.ICAO.value), self.redis, mode=REDIS_PREFIX.ICAO.value)
        for a in Airline._DB_IATA.values():
            a.save(key_path(REDIS_PREFIX.AIRLINES.value, REDIS_PREFIX.IATA.value), self.redis, mode=REDIS_PREFIX.IATA.value)

        a = dict([(k, v.getInfo()) for k, v in Airline._DB.items()])
        self.redis.json().set(key_path(REDIS_PREFIX.AIRLINES.value, REDIS_PREFIX.ICAO.value), Path.root_path(), a)
        a = dict([(k, v.getInfo()) for k, v in Airline._DB_IATA.items()])
        self.redis.json().set(key_path(REDIS_PREFIX.AIRLINES.value, REDIS_PREFIX.IATA.value), Path.root_path(), a)

        # temp
        a = [a.getInfo() for a in Airline._DB.values()]
        self.redis.json().set(key_path(REDIS_PREFIX.AIRLINES.value), Path.root_path(), a)

        logger.debug(f"loaded {len(Airline._DB)} airlines")
        return (True, f"LoadApp::loadAirlines: loaded airlines")

    def loadAirRoutes(self):
        logger.warning(f"no free global feed for airline routes")
        return (True, f"LoadApp::loadAirRoutes: no free global feed for airline routes")

    # #############################
    # AIRPORT MANAGER
    #
    def loadAirlineFrequencies(self):
        for k, v in self.airport.manager.airline_frequencies.items():
            self.redis.json().set(key_path(REDIS_PREFIX.AIRLINES.value, k), Path.root_path(), v)
        return (True, f"LoadApp::loadAirlineFrequencies: loaded airline frequencies")

    def loadAirlineRoutes(self):
        for k, v in self.airport.manager.airline_route_frequencies.items():
            for k1, v1 in v.items():
                self.redis.json().set(key_path(REDIS_PREFIX.AIRLINE_ROUTES.value, k), Path.root_path(), list(v.keys()))
                k2 = key_path(REDIS_PREFIX.AIRPORT_ROUTES.value, k1)
                if self.redis.json().get(k2) is None:
                    self.redis.json().set(k2, Path.root_path(), [k])
                else:
                    self.redis.json().arrappend(k2, Path.root_path(), k)
        return (True, f"LoadApp::loadAirlineRoutes: loaded airline routes")

    def loadAirlineRouteFrequencies(self):
        for k, v in self.airport.manager.airline_route_frequencies.items():
            for k1, v1 in v.items():
                self.redis.json().set(key_path(REDIS_PREFIX.AIRLINE_ROUTES.value, k, k1), Path.root_path(), v1)
                self.redis.json().set(key_path(REDIS_PREFIX.AIRPORT_ROUTES.value, k1, k), Path.root_path(), v1)
        return (True, f"LoadApp::loadAirlineRouteFrequencies: loaded airline route frequencies")

    def loadCompanies(self):
        for k, v in self.airport.manager.companies.items():
            self.redis.json().set(key_path(REDIS_PREFIX.COMPANIES.value, k), Path.root_path(), v.getInfo())
        for k, v in self.airport.manager.people.items():
            self.redis.json().set(key_path("business", "people", k), Path.root_path(), v)
        return (True, f"LoadApp::loadCompanies: loaded companies")

    def loadGSE(self):
        for k, v in self.airport.manager.equipment_by_type.items():
            for v1 in v:
                self.redis.json().set(key_path(REDIS_PREFIX.GSE.value, k, v1.getKey()), Path.root_path(), v1.getInfo())
        return (True, f"LoadApp::loadGSE: loaded GSE")

    def loadGSEFleet(self):
        fn = os.path.join(MANAGED_AIRPORT_DIR, "services", "equipment.yaml")
        with open(fn, "r") as file:
            data = yaml.safe_load(file)
            for f in data["equipment"]:
                for k, v in f.items():
                    self.redis.set("business:services:fleet:" + k, v)
        return (True, f"LoadApp::loadGSEFleet: loaded fleet")

    # #############################
    # MANAGED AIRPORT
    #
    def loadFlightPlans(self):
        flightplan_cache = os.path.join(MANAGED_AIRPORT_DIR, FLIGHTROUTE_DATABASE)
        for f in sorted(os.listdir(flightplan_cache)):
            if f.endswith(".json"):
                fn = os.path.join(flightplan_cache, f)
                kn = f.replace(".json", "").replace("-", ":").lower()
                with open(fn) as data_file:
                    data = json.load(data_file)
                    logger.debug(f"loading {fn}")
                    self.redis.json().set(key_path(REDIS_PREFIX.FLIGHTPLAN_FPDB.value, kn), Path.root_path(), data)
            if f.endswith(".geojson"):
                fn = os.path.join(flightplan_cache, f)
                kn = f.replace(".geojson", "").replace("-", ":").lower()
                with open(fn) as data_file:
                    data = json.load(data_file)
                    logger.debug(f"loading {fn}")
                    self.redis.json().set(key_path(REDIS_PREFIX.FLIGHTPLAN_GEOJ.value, kn), Path.root_path(), data)

        airportplan_cache = os.path.join(DATA_DIR, "airports", "fpdb")
        for f in sorted(os.listdir(airportplan_cache)):
            if f.endswith(".json"):
                fn = os.path.join(airportplan_cache, f)
                kn = f.replace(".json", "").replace("-", ":").lower()
                with open(fn) as data_file:
                    data = json.load(data_file)
                    logger.debug(f"loading {fn}")
                    self.redis.json().set(key_path(REDIS_PREFIX.FLIGHTPLAN_APTS.value, kn), Path.root_path(), data)

        return (True, f"LoadApp::loadFlightPlans: loaded flight plans")

    def loadRamps(self):
        for k, v in self.airport.ramps.items():
            if hasattr(v, "_resource"):
                del v._resource
            self.redis.json().set(
                key_path(REDIS_PREFIX.AIRPORT.value, REDIS_PREFIX.GEOJSON.value, REDIS_PREFIX.RAMPS.value, k), Path.root_path(), v.to_geojson()
            )
            self.redis.geoadd(REDIS_PREFIX.AIRPORT_GEO_INDEX.value, (v.lon(), v.lat(), key_path(POI_COMBO.RAMP.value, k)))

        logger.debug(f"loaded {len(self.airport.ramps)}")
        # logger.debug(f"loaded {self.airport.ramps}")
        return (True, f"LoadApp::loadRamps: loaded ramps")

    def loadRunways(self):
        for k, v in self.airport.runways.items():
            if hasattr(v, "end"):
                v.setProp("opposite-end", v.end.getProp("name"))
                logger.warning(f"removed circular dependency {v.getProp('name')} <> {v.end.getProp('name')}")
                del v.end
            if hasattr(v, "_resource"):
                del v._resource
            v.unsetProp("line")
            self.redis.json().set(
                key_path(REDIS_PREFIX.AIRPORT.value, REDIS_PREFIX.GEOJSON.value, REDIS_PREFIX.RUNWAYS.value, k), Path.root_path(), v.to_geojson()
            )

        logger.debug(f"loaded {len(self.airport.runways)}")
        return (True, f"LoadApp::loadRamps: loaded runways")

    def loadAirwayPOIS(self):
        for k, v in self.airport.aeroway_pois.items():
            self.redis.json().set(
                key_path(REDIS_PREFIX.AIRPORT.value, REDIS_PREFIX.GEOJSON.value, REDIS_PREFIX.AEROWAYS.value, k), Path.root_path(), v.to_geojson()
            )

        logger.debug(f"loaded {len(self.airport.aeroway_pois)}")
        return (True, f"LoadApp::loadAirwayPOIS: loaded airway points of interest")

    def loadServicePOIS(self):
        for k, v in self.airport.service_pois.items():
            self.redis.json().set(
                key_path(REDIS_PREFIX.AIRPORT.value, REDIS_PREFIX.GEOJSON.value, REDIS_PREFIX.GROUNDSUPPORT.value, k), Path.root_path(), v.to_geojson()
            )
            self.redis.geoadd(REDIS_PREFIX.AIRPORT_GEO_INDEX.value, (v.lon(), v.lat(), k))
            self.redis.geoadd(REDIS_PREFIX.AIRPORT_GEO_INDEX.value, (v.lon(), v.lat(), key_path(POI_COMBO.SERVICE.value, k)))

        logger.debug(f"loaded {len(self.airport.service_pois)}")
        return (True, f"LoadApp::loadServicePOIS: loaded service points of interest")

    # def loadServiceDestinations(self):
    #     for k, v in self.airport.service_destinations.items():
    #         self.redis.json().set(key_path(REDIS_PREFIX.AIRPORT.value, REDIS_PREFIX.GEOJSON.value, REDIS_PREFIX.GROUNDSUPPORT_DESTINATION.value, k), Path.root_path(), v)
    #         # self.redis.geoadd(REDIS_PREFIX.AIRPORT_GEO_INDEX.value, (v.lon(), v.lat(), k))

    #     logger.debug(f"loaded {len(self.airport.service_destinations)}")
    #     return (True, f"LoadApp::loadServiceDestinations: loaded service points of interest")

    def loadCheckpoints(self):
        for k, v in self.airport.check_pois.items():
            self.redis.json().set(
                key_path(REDIS_PREFIX.AIRPORT.value, REDIS_PREFIX.GEOJSON.value, REDIS_PREFIX.MISSION.value, k), Path.root_path(), v.to_geojson()
            )

        logger.debug(f"loaded {len(self.airport.check_pois)}")
        return (True, f"LoadApp::loadCheckpoints: loaded check points")

    # #############################
    # AIRSPACE
    #
    def loadVertices(self):
        # Vertices = Terminals + Navaids + Fixes = Waypoints
        HEARTBEAT = 10000
        cnt = 0
        errcnt = 0
        for k, v in self.airport.airspace.vert_dict.items():
            a = NamedPoint.parseId(ident=k)
            self.redis.json().set(key_path(REDIS_PREFIX.AIRSPACE_WAYPOINTS.value, k), Path.root_path(), v.getFeature())
            kr = key_path(REDIS_PREFIX.AIRSPACE_WAYPOINTS_INDEX.value, a[CPIDENT.IDENT])
            self.redis.sadd(kr, k)
            if cnt % HEARTBEAT == 0:
                logger.debug(f"{cnt}: {kr}, {k}")
            try:  # we noticed, experimentally, abs(lon) > 85 is not good...
                self.redis.geoadd(REDIS_PREFIX.AIRSPACE_WAYPOINTS_GEO_INDEX.value, (v.lon(), v.lat(), k))
            except:
                logger.debug(f"cannot load {k} (lat={v.lat()}, lon={v.lon()})")
                errcnt = errcnt + 1
            cnt = cnt + 1
        logger.debug(f"loaded {cnt}, {errcnt} errors")
        return (True, f"LoadApp::loadVertices: loaded")

    def loadTerminals(self):
        # Airports = Terminals
        cnt = 0
        errcnt = 0
        for k, v in self.airport.airspace.vert_dict.items():
            if isinstance(v, Terminal):
                a = NamedPoint.parseId(ident=k)
                self.redis.json().set(key_path(REDIS_PREFIX.AIRSPACE_TERMINALS.value, k), Path.root_path(), v.getInfo())
                self.redis.sadd(key_path(REDIS_PREFIX.AIRSPACE_ALL_INDEX.value, a[CPIDENT.IDENT]), k)
                try:  # we noticed, experimentally, abs(lon) > 85 is not good...
                    self.redis.geoadd(REDIS_PREFIX.AIRSPACE_WAYPOINTS_GEO_INDEX.value, (v.lon(), v.lat(), k))
                    cnt = cnt + 1
                except:
                    logger.debug(f"cannot load {v.icao} (lat={v.lat()}, lon={v.lon()})")
                    errcnt = errcnt + 1
        logger.debug(f"loaded {cnt}")
        return (True, f"LoadApp::loadTerminals: loaded terminals")

    def loadNavaids(self):
        cnt = 0
        for k, v in self.airport.airspace.vert_dict.items():
            if isinstance(v, NavAid):
                self.redis.json().set(key_path(REDIS_PREFIX.AIRSPACE_NAVAIDS.value, k), Path.root_path(), v.getInfo())
                a = NamedPoint.parseId(ident=k)
                # self.redis.sadd(key_path(REDIS_PREFIX.AIRSPACE_NAVAIDS_INDEX.value, a[CPIDENT.REGION], a[CPIDENT.IDENT]), k)
                self.redis.sadd(key_path(REDIS_PREFIX.AIRSPACE_ALL_INDEX.value, a[CPIDENT.IDENT]), k)
                self.redis.geoadd(REDIS_PREFIX.AIRSPACE_WAYPOINTS_GEO_INDEX.value, (v.lon(), v.lat(), k))
                cnt = cnt + 1
                cnt = cnt + 1
        logger.debug(f"loaded {cnt}")
        return (True, f"LoadApp::loadNavaids: loaded navaids")

    def loadFixes(self):
        cnt = 0
        errcnt = 0
        for k, v in self.airport.airspace.vert_dict.items():
            if isinstance(v, Fix):
                self.redis.json().set(key_path(REDIS_PREFIX.AIRSPACE_FIXES.value, k), Path.root_path(), v.getInfo())
                a = NamedPoint.parseId(ident=k)
                self.redis.sadd(key_path(REDIS_PREFIX.AIRSPACE_FIXES_INDEX.value, a[CPIDENT.REGION], a[CPIDENT.IDENT]), k)
                self.redis.sadd(key_path(REDIS_PREFIX.AIRSPACE_ALL_INDEX.value, a[CPIDENT.IDENT]), k)
                try:  # we noticed, experimentally, abs(lon) > 85 is not good...
                    self.redis.geoadd(REDIS_PREFIX.AIRSPACE_GEO_INDEX.value, (v.lon(), v.lat(), k))
                except:
                    logger.debug(f"cannot load {k} (lat={v.lat()}, lon={v.lon()})")
                    errcnt = errcnt + 1
                cnt = cnt + 1
        logger.debug(f"loaded {cnt}, {errcnt} errors")
        return (True, f"LoadApp::loadNavaids: loaded fixes")

    def loadHolds(self):
        cnt = 0
        for k, v in self.airport.airspace.holds.items():
            self.redis.json().set(key_path(REDIS_PREFIX.AIRSPACE_HOLDS.value, k), Path.root_path(), v.getInfo())
            try:
                self.redis.geoadd(REDIS_PREFIX.AIRSPACE_HOLDS_GEO_INDEX.value, (v.fix.lon(), v.fix.lat(), k))
            except:
                logger.debug(f"cannot load {k} (lat={v.fix.lat()}, lon={v.fix.lon()})")
            cnt = cnt + 1
        # We preselect holds in the vicinity of the managed airport
        logger.debug(f"preselecting {self.icao} local holds..")
        store = key_path(REDIS_PREFIX.AIRSPACE_HOLDS.value, self.icao)
        self.redis.geosearchstore(
            name=REDIS_PREFIX.AIRSPACE_HOLDS_GEO_INDEX.value,
            longitude=self.longitude,
            latitude=self.latitude,
            unit="km",
            radius=convert.km_to_nm(100),
            dest=store,
        )
        logger.debug(f"..stored in {store} ..done")
        #
        logger.debug(f"loaded {cnt}")
        return (True, f"LoadApp::loadHolds: loaded holding positions")

    def loadAirways(self):
        # ~ loadEdges.
        cnt = 0
        for v in self.airport.airspace.edges_arr:
            if isinstance(v, AirwaySegment):
                self.redis.json().set(key_path(REDIS_PREFIX.AIRSPACE_AIRWAYS.value, v.getKey()), Path.root_path(), v.getInfo())
                cnt = cnt + 1
        logger.debug(f"loaded {cnt}")
        return (True, f"LoadApp::loadAirways: loaded airways")

    def loadGraph(self, key, g):
        kbase = key_path("airport", key)
        kgeo = key_path("airport", key, "_geo_index")
        kn = key_path(kbase, "nodes")
        for k, v in g.vert_dict.items():
            self.redis.json().set(key_path(kn, k), Path.root_path(), v)
            self.redis.geoadd(kgeo, (v.lon(), v.lat(), k))
        kn = key_path(kbase, "edges")
        for e in g.edges_arr:
            self.redis.json().set(key_path(kn, e.getKey()), Path.root_path(), e)
            # self.redis.set(key_path(kn, e.getKey()), json.dumps(e))

    def loadAirspaces(self):
        cnt = 0
        for v in self.airport.airspace.airspaces.values():
            if isinstance(v, ControlledAirspace):
                payload = FeatureWithProps.convert(v).to_geojson()
                self.redis.json().set(key_path(REDIS_PREFIX.AIRSPACE_CONTROLLED.value, v.getProp("type"), str(v.getKey())), Path.root_path(), payload)
                cnt = cnt + 1
        logger.debug(f"loaded {cnt}")
        return (True, f"LoadApp::loadAirspaces: loaded controlled airspaces")

    # #############################
    # LISTS OF VALUES
    #
    def cache_lovs(self):
        def saveComboAsJson(k, arr):
            # redis.set(key_path(REDIS_DATABASE.LOVS.value,k),json.dumps(dict(arr)))
            k2 = key_path(REDIS_DATABASE.LOVS.value, k)
            d2 = dict(arr)
            self.redis.json().set(k2, Path.root_path(), jsonable_encoder(d2))

        logger.debug("caching..")

        # Airports operating at managed airport
        saveComboAsJson(REDIS_LOVS.AIRPORTS.value, Airport.getCombo())
        # Airlines operating at managed airport
        saveComboAsJson(REDIS_LOVS.AIRLINES.value, Airline.getCombo())
        # Airport ramps
        saveComboAsJson(REDIS_LOVS.RAMPS.value, self.airport.getRampCombo())
        # Airport runways
        saveComboAsJson(REDIS_LOVS.RUNWAYS.value, self.airport.getRunwayCombo())
        # Airport point of interest
        saveComboAsJson(REDIS_LOVS.POIS.value, self.airport.getPOICombo())
        # Airport handlers and operators
        saveComboAsJson(REDIS_LOVS.COMPANIES.value, self.airport.manager.getCompaniesCombo())
        # Aircraft types
        saveComboAsJson(REDIS_LOVS.AIRCRAFT_TYPES.value, AircraftTypeWithPerformance.getCombo())
        # # Services
        # redis.set(LOVS+"services", Service.getCombo())
        # # Service handlers
        # redis.set(LOVS+"service-handlers", self.airport.manager.getCompaniesCombo(classId="Service"))
        # # Missions
        # redis.set(LOVS+"service-handlers", Mission.getCombo())
        # # Mission handlers
        # redis.set(LOVS+"service-handlers", self.airport.manager.getCompaniesCombo(classId="Mission"))

        logger.debug("..done")
        return (True, f"LoadApp::cache_lovs: cached")


if __name__ == "__main__":
    """
    Exit: 0: Redis available, airport already loaded.
          1: Redis not available
          2: Redis available, whole airport is being loaded
          3: Redis available, airport already loaded, reloaded some data
    """
    not_connected = True
    attempts = 0
    logger.info(f"emitpy version {emitpy.__version__} «{emitpy.__version_name__}»")
    logger.debug("connecting to Redis..")
    while not_connected and attempts < REDIS_ATTEMPTS:
        r = redis.Redis(**REDIS_CONNECT)
        try:
            pong = r.ping()
            not_connected = False
            logger.debug("..connected.")
        except redis.RedisError:
            logger.debug(f"..cannot connect, retrying ({attempts+1}/{REDIS_ATTEMPTS}, sleeping {REDIS_WAIT} secs)..")
            attempts = attempts + 1
            time.sleep(REDIS_WAIT)

    if not_connected:
        logger.warning("..cannot connect to Redis. bye.")
        sys.exit(1)

    currdb = r.client_info()["db"]
    r.select(REDIS_DB.REF.value)
    k = key_path(REDIS_PREFIX.AIRPORT.value, MANAGED_AIRPORT_KEY)
    a = r.json().get(k)
    r.select(currdb)

    if a is None or MANAGED_AIRPORT_LAST_UPDATED not in a or AIRAC_CYCLE not in a and a["ICAO"] == MANAGED_AIRPORT_ICAO:
        logger.info(f"No managed airport: loading all..")
        d = LoadApp(icao=MANAGED_AIRPORT_ICAO)
        logger.debug(f"..loaded")
        sys.exit(2)

    if len(sys.argv) < 2:
        logger.info(f"Managed airport already loaded:")
        logger.info(json.dumps(a, indent=2))
        logger.info(f"use «{sys.argv[0]} '*'» to reload everying or list data to reload like «{sys.argv[0]} apt airway info»")
        logger.info(
            "you can load any of the following: actype, acperf, acequiv, actaprof, airport, airline, airroute, alfreq, alroute, alroutefreq, comp, gse, gsefleet, ramp, rwy, apoi, spoi, cpoi, info"
        )
    if len(sys.argv) > 1:
        logger.info(f"Managed airport: {a}")
        logger.debug(f"loading or updating {sys.argv[1:]}..")
        d = LoadApp(icao=MANAGED_AIRPORT_ICAO, data_to_load=sys.argv[1:])
        if "info" not in sys.argv[1:]:
            logger.info(f"Managed airport: info not updated")
        logger.debug(f"..updated")
        sys.exit(3)

    sys.exit(0)
