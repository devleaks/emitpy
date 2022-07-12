"""
A FlightPlanRoute is a route from origin to destination using airways in Airspace.
The Flight Route is computed from airports, navaids, fixes, and airways.
"""
import logging

from emitpy.graph import Route


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

        self.filename = f"{fromICAO.lower()}-{toICAO.lower()}"

        if self.airspace is not None:
            self.getFlightPlan()


    def setAirspace(self, airspace):
        self.airspace = airspace


    def nodes(self):
        if self.flight_plan is None:
            self.getFlightPlan()

        return self.flight_plan["route"] if self.flight_plan is not None else None


    def has_plan(self):
        return self.flight_plan is not None


    def getFlightPlan(self):
        if self.airspace is None:  # force fetch from flightplandb
            logger.warning(":getFlightPlan: no airspace")
            return None

        a = self.airspace

        # Resolving airports
        origin = a.getAirportICAO(self.fromICAO)
        if origin is None:
            logger.warning(f":getFlightPlan: cannot get airport {self.fromICAO}")
            return None
        destination = a.getAirportICAO(self.toICAO)
        if destination is None:
            logger.warning(f":getFlightPlan: cannot get airport {self.toICAO}")
            return None

        # Resolving network
        s = a.nearest_vertex(point=origin, with_connection=True)
        if s is None or s[0] is None:
            logger.warning(f":getFlightPlan: cannot get nearest point to {self.fromICAO}")
            return None
        e = a.nearest_vertex(point=destination, with_connection=True)
        if e is None or e[0] is None:
            logger.warning(f":getFlightPlan: cannot get nearest point to {self.toICAO}")
            return None

        # Routing
        logger.debug(f":getFlightPlan: from {s[0].id} to {e[0].id}..")
        if s[0] is not None and e[0] is not None:
            self.flight_plan = Route(self.airspace, s[0].id, e[0].id)
            # self.flight_plan.find()  # auto route
        logger.debug(f":getFlightPlan: ..done")
        return self.flight_plan
