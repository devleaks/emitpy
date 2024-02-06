#
import logging
import copy
import typing
from typing import List

from emitpy.geo.turf import Feature, LineString, FeatureCollection

from emitpy.graph import Route


logger = logging.getLogger("FlightRoute")


class FlightPlan:
    """Flight plan data

    A FlightPlan is a set of minimal data, mostly optional, that is supplied
    to the FlightRouteFilnder to set a few choices.
    It is used to build the lateral navigation.
    """

    def __init__(
        self,
        name: str,
        departure: str,
        arrival: str,
        departure_rwy: typing.Optional[str] = None,
        sid: typing.Optional[str] = None,
        cruise_alt: typing.Optional[str] = None,
        waypoints: List[str] = [],
        star: typing.Optional[str] = None,
        appch: typing.Optional[str] = None,
        final: typing.Optional[str] = None,
        arrival_rwy: typing.Optional[str] = None,
    ):
        """Create a new flight plan

        Minimal information is departure and arrival airport,
        one of which is expected to be the Managed Airport.
        Missing information will be more or less randomly seleccted,
        or using external information (weather).

        Args:
            name (str): Flight number
            departure (str): Departure airport
            arrival (str): Arrival airport
            waypoints (List[str] = []): List of waypoints in the flight plan
            departure_rwy (typing.Optional[str]): Departure runway
            sid (typing.Optional[str]): Departure SID procedure
            cruise_alt (typing.Optional[str]): Cruising altitude
            star (typing.Optional[str]): Arrival STAR procedure
            appch (typing.Optional[str]): Arrival approach procedure
            final (typing.Optional[str]): Arrival final procedure
            arrival_rwy (typing.Optional[str]): Arrival runway
        """
        self.name = name
        self.aerospace = None
        self.managedAirport = None
        self._departure = departure
        self._arrival = arrival
        self._departure_rwy = departure_rwy
        self._sid = sid
        self._cruise_alt = cruise_alt
        self._waypoints = waypoints
        self._star = star
        self._appch = appch
        self._final = final
        self._arrival_rwy = arrival_rwy
        self._randomized = False

    def __str__(self):
        """Return flight plan in one liner

        Example output:

        EBBR LIRSU UZ315 RIDAR UZ738 UNKEN UL603 LATLO 4700N01400E KFT VALLU PODET L603 ZAG P735 VBA M19 ETIDA Q27 ARTAT UP975 NOLDO P975 SIDAD UP975 LONOS UL438 MOGAS OTHH

        Returns:
            [type]: [description]
        """
        plan = ""
        return plan

    def is_arrival(self, managedAirport):
        return managedAirport.icao == self._arrival

    def make(self, aerospace, managedAirport, use_random: bool = False) -> bool:
        """Replace each input string with its airspace class equivalent.

        [description]

        Args:
            airspace ([type]): Airspace for airports, airways, procedures...
        """
        self.aerospace = aerospace
        self.managedAirport = managedAirport
        self._randomized = use_random
        return False

    def parse(self, flightplan: str) -> bool:
        """Attempt to parse elements from flight plan string.

        Populate this class' attributes.

        Args:
            flightplan (str): Flight plan as one string, token separated by space.
        """
        fparr = flightplan.split()
        if len(fparr) < 2:
            logger.warning(f"insuficient way points ({len(fparr)})")
            return False
        f0 = fparr[0]
        if f0.upper().endswith("(D)"):  # departure airport
            self._departure = f0.replace("(D)", "")
            del fparr[0]
            logger.debug(f"set departure airport {self._departure}")
        elif f0[-3:] in ["(P)", "(S)"]:
            self._sid = f0[:-3]
            del fparr[0]
            logger.debug(f"set departure procedure SID {self._sid}")
        elif self.aerospace.getAirportICAO(f0) is not None:
            self._departure = f0
            del fparr[0]
            logger.debug(f"set departure airport {self._departure}")
        f0 = fparr[-1]
        if f0.upper().endswith("(A)"):  # departure airport
            self._arrival = f0.replace("(A)", "")
            del fparr[-1]
            logger.debug(f"set arrival airport {self._arrival}")
        elif f0[-3:] in ["(P)", "(S)"]:
            self._star = f0[:-3]
            del fparr[-1]
            logger.debug(f"set arrival procedure STAR {self._star}")
        elif self.aerospace.getAirportICAO(f0) is not None:
            self._arrival = f0
            del fparr[0]
            logger.debug(f"set arrival airport {self._departure}")
        self._waypoints = fparr
        logger.debug(f"waypoints: {self._waypoints}")
        return True


class FlightRoute:
    """
    A FlightRoute is a flight plan built from navaid, fixes, and airways.
    If we do not find a route from departure to arrival, has_plan() returns False.
    """

    def __init__(
        self,
        managedAirport,
        fromICAO: str,
        toICAO: str,
        useNAT: bool = True,
        usePACOT: bool = True,
        useAWYLO: bool = True,
        useAWYHI: bool = True,
        cruiseAlt: float = 35000,
        cruiseSpeed: float = 420,
        ascentRate: float = 2500,
        ascentSpeed: float = 250,
        descentRate: float = 1500,
        descentSpeed: float = 250,
        force: bool = False,
        autoroute: bool = True,
    ):
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
            self.flight_plan = Route(a, s[0].id, e[0].id)  # self.flight_plan.find()  # auto route
            if self.flight_plan is not None and self.flight_plan.found():
                self._convertToGeoJSON()
            else:
                cnt = 10
                logger.warning(f"{'>' * cnt} no route from {self.fromICAO} to {self.toICAO} {'<' * cnt}")

        logger.debug(f"..done")

    def makeGreatCircleFlightRoute(self):
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
            self.flight_plan = Route(a, s[0].id, e[0].id, auto=False)
            self.flight_plan.direct()
            self._convertToGeoJSON()
            logger.warning(f"direct route from {self.fromICAO} to {self.toICAO}")
        logger.debug(f"..done")

    def makeFlightRouteFromPlan(self, flightplan: FlightPlan):
        """Build a flight route from the information available in the flight plan.

        If some information is missing, it is either selected randomly
        of set according to besic rules.

        Args:
            flightplan (FlightPlan): [description]
        """
        logger.debug(f"NOT IMPLEMENTED ({flightplan})")

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
        fp = []
        for n in self.nodes():
            f = a.get_vertex(n)
            fi = f.getId()
            fa = fi.split(":")
            if len(fa) == 4:
                fi = fa[1]
            fp.append(fi)
        return SEP.join(fp)

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
