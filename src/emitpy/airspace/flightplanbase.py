"""
A FlightPlan connects 2 airports without any reffinement.
A FlightPlanBase is a route from origin to destination using airways.
"""
# curl -u vMzb5J3qtRnIo4CgdCqiGUsRhWEXpAHLMJj04Rds: -i https://api.flightplandatabase.com/
import os
import json
import requests_cache

import flightplandb as fpdb
from flightplandb.datatypes import GenerateQuery
from flightplandb.exceptions import BaseErrorHandler

from geojson import Feature, LineString, Point, FeatureCollection

from emitpy.constants import REDIS_PREFIX, REDIS_DB
from emitpy.utils import FT, key_path, rejson
from emitpy.private import FLIGHT_PLAN_DATABASE_APIKEY
from emitpy.parameters import DEVELOPMENT, PRODUCTION, DATA_DIR

import logging


logger = logging.getLogger("FlightPlanBase")


class FlightPlanBase:
    def __init__(self, managedAirport, fromICAO: str, toICAO: str,
                 useNAT: bool = True, usePACOT: bool = True, useAWYLO: bool = True, useAWYHI: bool = True,
                 cruiseAlt: float = 35000, cruiseSpeed: float = 420,
                 ascentRate: float = 2500, ascentSpeed: float = 250,
                 descentRate: float = 1500, descentSpeed: float = 250,
                 force: bool = False):

        self.managedAirport = managedAirport
        self.fromICAO = fromICAO
        self.toICAO = toICAO
        self.cruiseAlt = cruiseAlt
        self.cruiseSpeed = cruiseSpeed
        self.ascentRate = ascentRate
        self.ascentSpeed = ascentSpeed
        self.descentRate = descentRate
        self.descentSpeed = descentSpeed
        self.useNAT = useNAT
        self.usePACOT = usePACOT
        self.useAWYLO = useAWYLO
        self.useAWYHI = useAWYHI
        self.force = force
        self.flight_plan = None
        self.route = None
        self.routeLS = None
        self.redis = managedAirport.redis

        # creates file caches
        self.flightplan_cache = os.path.join(DATA_DIR, "managedairport", managedAirport.airport.icao, "flightplans")
        if not os.path.exists(self.flightplan_cache):
            logger.warning(":init: no file plan cache directory")
            if redis is None:
                logger.warning(":init: no Redis, creating directory")
                pathlib.Path(self.flightplan_cache).mkdir(parents=True, exist_ok=True)
            #print("create new fpdb file cache")
            #os.mkdir(self.flightplan_cache)

        self.airports_cache = os.path.join(DATA_DIR, "airports", "fpdb")
        if not os.path.exists(self.airports_cache):
            logger.warning(":init: no airport cache directory")
            if redis is None:
                logger.warning(":init: no Redis, creating directory")
                pathlib.Path(self.airports_cache).mkdir(parents=True, exist_ok=True)
            #print("create new fpdb file cache")
            #os.mkdir(self.flightplan_cache)

        self.filename = f"{fromICAO.lower()}-{toICAO.lower()}"
        if FLIGHT_PLAN_DATABASE_APIKEY is None or FLIGHT_PLAN_DATABASE_APIKEY == "":
            logger.warning(":init: no api key to flightplandatabase, no new route will be computed from flight plan database")

        # For development
        if DEVELOPMENT or not PRODUCTION:
            if self.redis is not None:
                backend = requests_cache.RedisCache(connection=managedAirport.redis, db=2)
                requests_cache.install_cache(backend=backend)
            else:
                requests_cache.install_cache()  # defaults to sqlite

        self.getFlightPlan()


    def has_plan(self):
        # if (self.flight_plan is not None) and ('route' in self.flight_plan) and ('nodes' in self.flight_plan['route']):
        #     logger.debug(f"has plan: {len(self.flight_plan['route']['nodes'])} nodes")
        # else
        #     logger.debug(f"has no plan")
        return self.flight_plan is not None and len(self.flight_plan["route"]["nodes"]) > 0


    def nodes(self):
        if self.flight_plan is None:
            self.getFlightPlan()

        return self.flight_plan["route"]["nodes"] if self.flight_plan is not None else None


    def getFlightPlan(self):
        if self.force:  # force fetch from flightplandb
            return self.fetchFlightPlan()

        if self.flight_plan is not None:
            return self.flight_plan


        if self.redis is not None:
            ffp = key_path(REDIS_PREFIX.FLIGHTPLAN_FPDB.value, self.fromICAO.lower(), self.toICAO.lower())
            self.flight_plan = rejson(redis=self.redis, key=ffp, db=REDIS_DB.REF.value)
            if self.flight_plan is not None:
                self._convertToGeoJSON()
                logger.debug(f"getFlightPlan: {self.flight_plan['id']} from Redis cache {ffp}")
                return self.flight_plan
        else:
            ffp = os.path.join(self.flightplan_cache, self.filename + ".json")
            if os.path.exists(ffp):
                with open(ffp, "r") as file:
                    self.flight_plan = json.load(file)
                    self._convertToGeoJSON()
                    logger.debug(f"getFlightPlan: {self.flight_plan['id']} from file cache {ffp}")
                return self.flight_plan

        logger.debug(f"getFlightPlan: no cached plan {ffp}, fetching from database")
        return self.fetchFlightPlan()


    def _convertToGeoJSON(self):
        # convert the route of a flight plan to a geojson feature collection
        # of waypoints and a line segment for the route.
        self.routeLS = LineString()
        self.route = FeatureCollection(features=[])

        for n in self.flight_plan["route"]["nodes"]:
            self.route.features.append(Feature(geometry=Point((n["lon"], n["lat"], n["alt"]*FT)), properties={
                "type": n["type"],
                "ident": n["ident"],
                "name": n["name"],
                "via": n["via"],
            }))
            self.routeLS.coordinates.append([n["lon"], n["lat"], n["alt"]*FT])


    def fetchFlightPlan(self):
        fpid = None
        plans = None

        try:
            plans = fpdb.user.plans(username="devleaks", limit=1000)
        except BaseErrorHandler:
            logger.warning("fetchFlightPlan: error from server fetching plans")

        if plans is not None:
            for plan in plans:
                if fpid is None:
                    if plan.fromICAO == self.fromICAO and plan.toICAO == self.toICAO:
                        fpid = plan.id
            if fpid is not None:  # cache it
                try:
                    fp = fpdb.plan.fetch(id_=fpid, return_format="json")
                    # @todo should check for error status...
                    self.flight_plan = json.loads(fp)
                    logger.debug("fetchFlightPlan: %d from FPDB" % (self.flight_plan["id"]))
                    self.cacheFlightPlan()
                    return self.flight_plan
                except BaseErrorHandler:
                    logger.warning("fetchFlightPlan: error from server fetching plan")

        return self.createFPDBFlightPlan()


    def cacheFlightPlan(self, geojson: bool = True):
        fn = os.path.join(self.flightplan_cache, self.filename + ".json")
        with open(fn, "w") as outfile:
            json.dump(self.flight_plan, outfile)
            logger.debug("%d now cached in file %s" % (self.flight_plan["id"], fn))
        if geojson:
            self._convertToGeoJSON()
            geo = self.getGeoJSON(include_ls=True)
            fngeo = os.path.join(self.flightplan_cache, self.filename + ".geojson")
            with open(fngeo, "w") as outfile:
                json.dump(geo, outfile)
                logger.debug("geojson %d now cached in file %s" % (self.flight_plan["id"], fngeo))

        logger.debug("%d now cached in file %s" % (self.flight_plan["id"], fn))
        self.cacheAirports()


    def createFPDBFlightPlan(self):
        plan_data = GenerateQuery(
            fromICAO=self.fromICAO,
            toICAO=self.toICAO
            #, # not used
            #cruiseAlt=self.cruiseAlt,
            #cruiseSpeed=self.cruiseSpeed,
            #ascentRate=self.ascentRate,
            #ascentSpeed=self.ascentSpeed,
            #descentRate=self.descentRate,
            #descentSpeed=self.descentSpeed
        )
        try:
            plan = fpdb.plan.generate(plan_data)
            if plan:
                try:
                    fp = fpdb.plan.fetch(id_=plan.id, return_format="json")
                    # @todo should check for error status...
                    self.flight_plan = json.loads(fp)
                    logger.debug("createFPDBFlightPlan: new plan %d" % (self.flight_plan["id"]))
                    self.cacheFlightPlan(geojson=True)
                    return self.flight_plan
                except BaseErrorHandler:
                    logger.warning("createFPDBFlightPlan: error from server when trying to fetch plan")

        except BaseErrorHandler:
            logger.warning("createFPDBFlightPlan: error from server when trying to generate")

        return None


    def cacheAirports(self):
        """
        We cache airport data because it contains interesting information like elevation.
        """
        for f in [self.fromICAO, self.toICAO]:
            fn = os.path.join(self.airports_cache, f + ".json")
            if not os.path.exists(fn) or os.stat(fn).st_size == 0 or self.force:
                try:
                    aptresp = fpdb.nav.airport(icao=f)
                    apt = aptresp._to_api_dict()
                    with open(fn, "w") as outfile:
                        json.dump(apt, outfile)
                        logger.debug(f"cacheAirports: new airport {f}")
                except BaseErrorHandler:
                    logger.warning(f"cacheAirports: error from server for airport {f}")


    def getFPDBAirport(self, icao: str):
        fn = os.path.join(self.airports_cache, icao + ".json")
        if os.path.exists(fn):
            with open(fn, "r") as file:
                airport = json.load(file)
                logger.debug("getFPDBAirport: %d from file cache %s" % (icao, fn))
                return airport
        else:
            logger.warning("getFPDBAirport: airport %d not found in file cache %s" % (icao, fn))
        return None
