"""
A FlightPlan is a flight plan built at from navaid, fixes, and airways.
If we do not find a route from departure to arrival, has_plan() returns False.
"""
import logging
import copy

from geojson import Feature, LineString, Point, FeatureCollection

from emitpy.graph import Route


logger = logging.getLogger("FlightRoute")


class FlightRoute:

    def __init__(self, managedAirport, fromICAO: str, toICAO: str,
                 useNAT: bool = True, usePACOT: bool = True, useAWYLO: bool = True, useAWYHI: bool = True,
                 cruiseAlt: float = 35000, cruiseSpeed: float = 420,
                 ascentRate: float = 2500, ascentSpeed: float = 250,
                 descentRate: float = 1500, descentSpeed: float = 250,
                 force: bool = False, autoroute: bool = True):

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
        self._route = None
        self.routeLS = None
        self.waypoints = None

        self.filename = f"{fromICAO.lower()}-{toICAO.lower()}"

        if autoroute:
            self.makeFlightRoute()


    def getAirspace(self):
        return self.managedAirport.airport.airspace


    def nodes(self):
        if self.flight_plan is None:
            self.makeFlightRoute()

        return self.flight_plan.route if self.flight_plan is not None else None


    def has_route(self):
        return self.flight_plan is not None and self.flight_plan.found()


    def makeFlightRoute(self):
        a = self.getAirspace()

        if a is None:  # force fetch from flightplandb
            logger.warning(":makeFlightRoute: no airspace")
            return None

        # Resolving airports
        origin = a.getAirportICAO(self.fromICAO)
        if origin is None:
            logger.warning(f":makeFlightRoute: cannot get airport {self.fromICAO}")
            return None
        destination = a.getAirportICAO(self.toICAO)
        if destination is None:
            logger.warning(f":makeFlightRoute: cannot get airport {self.toICAO}")
            return None

        # Resolving network
        s = a.nearest_vertex(point=origin, with_connection=True)
        if s is None or s[0] is None:
            logger.warning(f":makeFlightRoute: cannot get nearest point to {self.fromICAO}")
            return None
        e = a.nearest_vertex(point=destination, with_connection=True)
        if e is None or e[0] is None:
            logger.warning(f":makeFlightRoute: cannot get nearest point to {self.toICAO}")
            return None

        # Routing
        logger.debug(f":makeFlightRoute: from {s[0].id} to {e[0].id}..")
        if s[0] is not None and e[0] is not None:
            self.flight_plan = Route(a, s[0].id, e[0].id) # self.flight_plan.find()  # auto route
            if self.flight_plan is not None and self.flight_plan.found():
                self._convertToGeoJSON()
            else:
                logger.warning(f":makeFlightRoute: !!!!! no route from {self.fromICAO} to {self.toICAO} !!!!!")

        logger.debug(f":makeFlightRoute: ..done")


    def _convertToGeoJSON(self):
        # convert the route of a flight plan to a geojson feature collection
        # of waypoints and a line segment for the route.
        a = self.getAirspace()

        self.routeLS = LineString()
        self._route = FeatureCollection(features=[])
        self.waypoints = []

        logger.debug(f":_convertToGeoJSON: doing..")
        for n in self.nodes():
            f = a.get_vertex(n)
            self._route.features.append(f)
            self.routeLS.coordinates.append(f["geometry"]["coordinates"])
            self.waypoints.append(f)
        logger.debug(f":_convertToGeoJSON: ..done")


    def route(self):
        # returns flight route from airspace vertices, returns a copy because Feature properties will be modified
        return copy.deepcopy(self.waypoints)


    def getGeoJSON(self, include_ls: bool = False):
        # returns flight route from airspace vertices in GeoJSON FeatureCollection
        fc = copy.deepcopy(self._route)
        if include_ls:
            fc.features.append(Feature(geometry=self.routeLS, properties={"tag": "route"}))
        return fc
