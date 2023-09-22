#
import logging
import copy

from emitpy.geo.turf import Feature, LineString, Point, FeatureCollection

from emitpy.graph import Route


logger = logging.getLogger("FlightRoute")


class FlightRoute:
    """
    A FlightRoute is a flight plan built at from navaid, fixes, and airways.
    If we do not find a route from departure to arrival, has_plan() returns False.
    """

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
        """
        Gets the airspace.
        """
        return self.managedAirport.airport.airspace


    def nodes(self):
        """
        Returns the flight plan route as a collection of nodes.
        """
        if self.flight_plan is None:
            self.makeFlightRoute()

        return self.flight_plan.route if self.flight_plan is not None else None


    def has_route(self):
        """
        Returns whether a route is found.
        """
        return self.flight_plan is not None and self.flight_plan.found()


    def makeFlightRoute(self):
        """
        Builds the flight route between fromICAO and toICAO airports.
        """
        a = self.getAirspace()

        if a is None:  # force fetch from flightplandb
            logger.warning("no airspace")
            return None

        # Resolving airports
        origin = a.getAirportICAO(self.fromICAO)
        if origin is None:
            logger.warning(f"cannot get airport {self.fromICAO}")
            return None
        destination = a.getAirportICAO(self.toICAO)
        if destination is None:
            logger.warning(f"cannot get airport {self.toICAO}")
            return None

        # Resolving network
        s = a.nearest_vertex(point=origin, with_connection=True)
        if s is None or s[0] is None:
            logger.warning(f"cannot get nearest point to {self.fromICAO}")
            return None
        e = a.nearest_vertex(point=destination, with_connection=True)
        if e is None or e[0] is None:
            logger.warning(f"cannot get nearest point to {self.toICAO}")
            return None

        # Routing
        logger.debug(f"from {s[0].id} to {e[0].id}..")
        if s[0] is not None and e[0] is not None:
            self.flight_plan = Route(a, s[0].id, e[0].id) # self.flight_plan.find()  # auto route
            if self.flight_plan is not None and self.flight_plan.found():
                self._convertToGeoJSON()
            else:
                logger.warning(f"!!!!! no route from {self.fromICAO} to {self.toICAO} !!!!!")

        logger.debug(f"..done")


    def _convertToGeoJSON(self):
        """
        Convert the route of a flight plan to a geojson feature collection
        of waypoints and a line segment for the route.
        """
        a = self.getAirspace()

        logger.debug(f"doing..")
        self._route = FeatureCollection(features=[])
        self.waypoints = []
        ls_coords = []
        for n in self.nodes():
            f = a.get_vertex(n)
            self._route.features.append(f)
            ls_coords.append(f.coords())
            self.waypoints.append(f)
        self.routeLS = LineString(ls_coords)
        logger.debug(f"..done")


    def route(self):
        """
        Returns flight route from airspace vertices,
        returns a copy because Feature properties will be modified
        """
        return copy.deepcopy(self.waypoints)


    def print(self):
        """
        Print flight route in "flight plan" format
        """
        a = self.getAirspace()
        SEP = ","
        fp = ""
        for n in self.nodes():
            f = a.get_vertex(n)
            fi = f.getId()
            fa = fi.split(":")
            if len(fa) == 4:
                fi = fa[1]
            fp = fp + fi + SEP
        return fp.strip(SEP)


    def getGeoJSON(self, include_ls: bool = False):
        """
        Returns flight route from airspace vertices in GeoJSON FeatureCollection

        :param      include_ls:  Indicates if the ls is included
        :type       include_ls:  bool
        """
        fc = copy.deepcopy(self._route)
        if include_ls:
            fc.features.append(Feature(geometry=self.routeLS, properties={"tag": "route"}))
        return fc
