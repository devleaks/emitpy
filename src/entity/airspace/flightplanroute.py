"""
A FlightPlanRoute is a route from origin to destination using airways in Airspace.
The Flight Route is computed from airports, navaids, fixes, and airways.
"""
import os
import logging

from ..graph import Route

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("FlightPlanRoute")


class FlightPlanRoute:
    def __init__(self, managedAirport: str, fromICAO: str, toICAO: str,
                 useNAT: bool = True, usePACOT: bool = True, useAWYLO: bool = True, useAWYHI: bool = True,
                 cruiseAlt: float = 35000, cruiseSpeed: float = 420,
                 ascentRate: float = 2500, ascentSpeed: float = 250,
                 descentRate: float = 1500, descentSpeed: float = 250,
                 force: bool = False):

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
        self.airspace = None

        # creates file caches
        self.flightplan_cache = os.path.join("..", "data", "managedairport", managedAirport, "flightroutes")
        if not os.path.exists(self.flightplan_cache):
            logger.warning("no file plan cache directory")
            #print("create new fpdb file cache")
            #os.mkdir(self.flightplan_cache)

        self.filename = f"{fromICAO.lower()}-{toICAO.lower()}"


    def setAirspace(self, airspace):
        self.airspace = airspace


    def nodes(self):
        if self.flight_plan is None:
            self.getFlightPlan()

        return self.flight_plan["route"] if self.flight_plan is not None else None


    def getFlightPlan(self):
        if self.airspace is None:  # force fetch from flightplandb
            logger.warning(":getFlightPlan: no airspace")
            return None

        a = self.airspace
        origin = a.getAirportICAO(self.fromICAO)
        destination = a.getAirportICAO(self.toICAO)
        print(origin, destination)
        s = a.nearest_vertex(point=origin, with_connection=True)
        e = a.nearest_vertex(point=destination, with_connection=True)
        print(s[0].id, e[0].id)
        if s[0] is not None and e[0] is not None:
            self.flight_plan = Route(self.airspace, s[0].id, e[0].id)
            # self.flight_plan.find()  # auto route
        return self.flight_plan
