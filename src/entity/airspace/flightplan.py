"""
FlightPlan
"""
# curl -u vMzb5J3qtRnIo4CgdCqiGUsRhWEXpAHLMJj04Rds: -i https://api.flightplandatabase.com/
import os
import json
from geojson import Feature, LineString, Point, FeatureCollection
from ..constants import FOOT
from ..private import FLIGHT_PLAN_DATABASE_APIKEY
import flightplandb as fpdb
from flightplandb.datatypes import GenerateQuery

import requests_cache

import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("FlightRoute")

FP_DIR = os.path.join("..", "data", "flightplans")


class FlightPlan:
    def __init__(self, fromICAO: str, toICAO: str,
                 useNAT: bool = True, usePACOT: bool = True, useAWYLO: bool = True, useAWYHI: bool = True,
                 cruiseAlt: float = 35000, cruiseSpeed: float = 420,
                 ascentRate: float = 2500, ascentSpeed: float = 250,
                 descentRate: float = 1500, descentSpeed: float = 250):

        self.fromICAO = fromICAO
        self.toICAO = toICAO
        self.cruiseAlt = cruiseAlt
        self.cruiseSpeed = cruiseSpeed
        self.ascentRate = ascentRate
        self.ascentSpeed = ascentSpeed
        self.descentRate = descentRate
        self.descentSpeed = descentSpeed

        self.flight_plan = None
        self.route = None
        self.routeLS = None

        # creates file cache
        if not os.path.exists(FP_DIR):
            logger.warn("no file plan directory")
            #print("create new fpdb file cache")
            #os.mkdir(FP_DIR)

        self.filename = "%s-%s" % (fromICAO.lower(), toICAO.lower())
        self.api = fpdb.FlightPlanDB(FLIGHT_PLAN_DATABASE_APIKEY)

        # For development
        requests_cache.install_cache()

        self.cacheAirports()


    def to_geojson(self):
        # convert the route of a flight plan to a geojson feature collection
        # of waypoints and a line segment for the route.
        self.routeLS = LineString()
        self.route = FeatureCollection(features=[])

        for n in self.flight_plan["route"]["nodes"]:
            self.route.features.append(Feature(geometry=Point((n["lon"], n["lat"], n["alt"]*FOOT)), properties={
                "type": n["type"],
                "ident": n["ident"],
                "name": n["name"]
            }))
            self.routeLS.coordinates.append([n["lon"], n["lat"], n["alt"]*FOOT])


    def getGeoJSON(self, include_ls: bool = False):
        # fluke-ignore F841
        dummy = self.getFlightPlan()
        if self.route is not None:
            fc = FeatureCollection(features=self.route.features)  # .copy()
            if include_ls:
                fc.features.append(Feature(geometry=self.routeLS, properties={"tag": "route"}))
            return fc

        return None


    def getFlightPlan(self):
        if self.flight_plan is not None:
            return self.flight_plan

        ffp = os.path.join(FP_DIR, self.filename + ".json")

        if os.path.exists(ffp):
            with open(ffp, "r") as file:
                self.flight_plan = json.load(file)
                self.to_geojson()
                logger.debug("FlightRoute: %d from file cache %s" % (self.flight_plan["id"], ffp))

            return self.flight_plan

        return self.getFPDBFlightPlan()


    def getFPDBFlightPlan(self):
        fpid = None
        plans = self.api.user.plans(username="devleaks", limit=1000)
        # @todo should check for error status...

        for plan in plans:
            if fpid is None:
                if plan.fromICAO == self.fromICAO and plan.toICAO == self.toICAO:
                    fpid = plan.id

        if fpid is not None:  # cache it
            fp = self.api.plan.fetch(id_=fpid, return_format="json")
            # @todo should check for error status...
            self.flight_plan = json.loads(fp)
            logger.debug("FlightRoute: %d from FPDB" % (self.flight_plan["id"]))
            self.cacheFlightPlan()
            return self.flight_plan

        return self.createFPDBFlightPlan()


    def cacheFlightPlan(self, geojson: bool = True):
        fn = os.path.join(FP_DIR, self.filename + ".json")
        with open(fn, "w") as outfile:
            json.dump(self.flight_plan, outfile)
            logger.debug("%d now cached in file %s" % (self.flight_plan["id"], fn))
        if geojson:
            self.to_geojson()
            geo = self.getGeoJSON(include_ls=True)
            fngeo = os.path.join(FP_DIR, self.filename + ".geojson")
            with open(fngeo, "w") as outfile:
                json.dump(geo, outfile)
                logger.debug("geojson %d now cached in file %s" % (self.flight_plan["id"], fngeo))

        logger.debug("%d now cached in file %s" % (self.flight_plan["id"], fn))
        self.cacheAirports()


    def createFPDBFlightPlan(self):
        plan_data = GenerateQuery(
            fromICAO=self.fromICAO,
            toICAO=self.toICAO
            #, # not used...
            #cruiseAlt=self.cruiseAlt,
            #cruiseSpeed=self.cruiseSpeed,
            #ascentRate=self.ascentRate,
            #ascentSpeed=self.ascentSpeed,
            #descentRate=self.descentRate,
            #descentSpeed=self.descentSpeed
            )
        plan = self.api.plan.generate(plan_data)
        # @todo should check for error status... (or try/catch)
        if plan:
            fp = self.api.plan.fetch(id_=plan.id, return_format="json")
            # @todo should check for error status...
            self.flight_plan = json.loads(fp)
            logger.debug("FlightRoute: new plan %d" % (self.flight_plan["id"]))
            self.cacheFlightPlan(geojson=True)
            return self.flight_plan

        return None


    def cacheAirports(self):
        """
        We cache airport data because it contains interesting information like elevation.
        """
        for f in [self.fromICAO, self.toICAO]:
            fn = os.path.join(FP_DIR, "airports", f + ".json")
            if not os.path.exists(fn) or os.stat(fn).st_size == 0:
                aptresp = self.api.nav.airport(icao=f)
                apt = aptresp._to_api_dict()
                with open(fn, "w") as outfile:
                    json.dump(apt, outfile)
                    logger.debug("FlightRoute: new airport %s" % (f))

