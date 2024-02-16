# Airspace Utility Classes
# With the exception of the restriction-related classes, all utility classes are GeoJSON features.
# The Airspace class is a network of air routes. It is an abstract class for building application-usable airspaces
# used for aircraft movements.
#
from __future__ import annotations
import os
import pickle
import logging
import math
import json
from abc import ABC, abstractmethod
from typing import Dict, List
from enum import Enum

from emitpy.constants import ID_SEP
from emitpy.geo.turf import Point, LineString
from emitpy.geo.turf import distance

from emitpy.graph import Vertex, Edge, Graph
from emitpy.geo import FeatureWithProps
from emitpy.utils import key_path

logger = logging.getLogger("Airspace")


class CPIDENT(Enum):
    REGION = "region"
    AIRPORT = "airport"
    IDENT = "ident"
    POINTTYPE = "pointtype"


################################
#
# CONTROLLED POINTS (ABSTRACT CLASSES)
#
#
class NamedPoint(Vertex):
    """
    A NamedPoint is a named point in a controlled airspace region.
    """

    def __init__(self, ident: str, region: str, airport: str, pointtype: str, lat: float, lon: float):
        name = NamedPoint.mkId(region, airport, ident, pointtype)
        Vertex.__init__(self, node=name, point=Point((lon, lat)))
        self.ident = ident
        self.region = region
        self.airport = airport

    @staticmethod
    def mkId(region: str, airport: str, ident: str, pointtype: str | None = None) -> str:
        """
        Builds a NamedPoint identifier from its region, airport (or enroute),
        identifier and point type (Fix, navaid, etc.)

        :param      region:     The region
        :type       region:     str
        :param      airport:    The airport
        :type       airport:    str
        :param      ident:      The identifier
        :type       ident:      str
        :param      pointtype:  The pointtype
        :type       pointtype:  str

        :returns:   { description_of_the_return_value }
        :rtype:     str
        """
        return ID_SEP.join([region, ident, ("" if pointtype is None else pointtype), airport])

    @staticmethod
    def parseId(ident: str):
        """
        Reconstruct an identifier built by mkId function into its constituting parts.

        :param      ident:  The identifier
        :type       ident:  str
        """
        arr = ident.split(ID_SEP)
        return {CPIDENT.REGION: arr[0], CPIDENT.IDENT: arr[1], CPIDENT.POINTTYPE: arr[2], CPIDENT.AIRPORT: arr[3]} if len(arr) == 4 else None

    def getInfo(self):
        """
        Gets a NamedPoint information dictionary.
        """
        return {"class": type(self).__name__, "name": self.name, "ident": self.ident, "region": self.region, "airport": self.airport}  # from Vertex()

    def getFeature(self):
        """
        Get a simple, clean GeoJSON feature from the NamedPoint.

        Actually, test if serialisation would/will work, if not create a new Feature from it.
        """
        try:
            s = json.dumps(self)
            # if succeeded:
            return self
        except:
            # else, tries a simpler version
            return FeatureWithProps.new(self)

    def getIdent(self):
        return self.ident


################################
#
# N A V A I D S
#
#
class NavAid(NamedPoint):
    """
    Base class for all navigational aids.
    """

    # 46.646819444 -123.722388889  AAYRR KSEA K1 4530263
    def __init__(self, ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, name):
        # for marker beacons, we use their "name"/type (OM/MM/IM) rather than a generic MB (marker beacon)
        NamedPoint.__init__(self, ident, region, airport, type(self).__name__ if type(self).__name__ != "MB" else name, lat, lon)
        self.elev = elev
        self.freq = freq
        self.ndb_class = ndb_class
        self.ndb_ident = ndb_ident
        self.name = name


class NDB(NavAid):  # 2
    """
    Non Directional Beacon
    """

    def __init__(self, ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, name):
        NavAid.__init__(self, ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, name)


class VOR(NavAid):  # 3
    """
    VHF Omnidirectional Range
    """

    def __init__(self, ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, name):
        NavAid.__init__(self, ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, name)


class LOC(NavAid):  # 4,5
    """
    Localiser
    """

    def __init__(self, ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, runway, name):
        NavAid.__init__(self, ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, name)
        self.runway = runway


class GS(NavAid):  # 6
    """
    GLide slope component of an ILS
    """

    def __init__(self, ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, runway, name):
        NavAid.__init__(self, ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, name)
        self.runway = runway


class MB(NavAid):  # 7,8,9
    """
    Marker Beacon, outer, middle or inner.
    """

    def __init__(self, ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, runway, name):
        NavAid.__init__(self, ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, name)
        self.runway = runway


class DME(NavAid):  # 12,13
    """
    Distance Measuring Equipment
    """

    def __init__(self, ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, name):
        NavAid.__init__(self, ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, name)


class FPAP(NavAid):  # 14
    """
    Final approach path alignment point (SBAS and GBAS)
    """

    def __init__(self, ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, runway, name):
        NavAid.__init__(self, ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, name)
        self.runway = runway


class GLS(NavAid):  # 16
    """
    GBAS Landing System
    """

    def __init__(self, ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, runway, name):
        NavAid.__init__(self, ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, name)
        self.runway = runway


class LTPFTP(NavAid):  # 16
    """
    Landing threshold point or fictitious threshold point of an SBAS/GBAS approach
    """

    def __init__(self, ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, runway, name):
        NavAid.__init__(self, ident, region, airport, lat, lon, elev, freq, ndb_class, ndb_ident, name)
        self.runway = runway


################################
#
# F I X E S
#
#
class Fix(NamedPoint):
    """
    Non navigational aid fix.
    (we currently do not store how the fix is located, relative to surrounding navaids.)
    """

    # 1150: 46.646819444 -123.722388889  AAYRR KSEA K1 4530263
    # 1200: 46.646819444 -123.722388889  AAYRR KSEA K1 4530263 AAYRR
    def __init__(self, ident, region, airport, lat, lon, waypoint_type: str, spoken_name: str | None = None):
        NamedPoint.__init__(self, ident, region, airport, type(self).__name__, lat, lon)
        self.waypoint_type = self.decode_waypoint_type(waypoint_type)
        self.spoken_name = spoken_name

    def decode_waypoint_type(self, s: str) -> str:
        """32bit representation of the 3-byte field defined by ARINC 424.18 field type definition 5.42, with the 4th byte set to 0 in Little Endian byte order."""
        i = int(s)
        b = i.to_bytes(4, "little")
        return b.decode("utf-8")


################################
#
# A I R P O R T S
#
#
class Terminal(NamedPoint):
    """
    This Terminaml is a NamedPoint airport.
    """

    AS_WAYPOINTS: Dict[str, Terminal] = {}

    def __init__(self, name: str, lat: float, lon: float, alt: float, iata: str, longname: str, country: str, city: str):
        NamedPoint.__init__(self, ident=name, region=name[0:2], airport=name, pointtype=type(self).__name__, lat=lat, lon=lon)
        self.iata = iata
        self.icao = name
        self.country = country
        self.city = city
        # logger.debug(f"Terminal:__init__: name: {self.id} / {name[0:2]}:{iata} / {longname}")
        self.longname = longname
        self._as_waypoint = f"{name[0:2]}:{iata}"
        Terminal.AS_WAYPOINTS[self._as_waypoint] = self  # keep region:iata name for reference in lnav
        self.setAltitude(alt)

    @staticmethod
    def as_waypoint(name):
        return Terminal.AS_WAYPOINTS[name] if name in Terminal.AS_WAYPOINTS.keys() else None

    def getKey(self):
        return key_path(self.icao[0:2], self.icao[2:4])

    def getInfo(self):
        i = super().getInfo()
        i.update({"iata": self.iata, "icao": self.icao, "country": self.country, "city": self.city, "longname": self.longname})
        return i


################################
#
# W A Y P O I N T S
#
# AND OTHER SPECIAL POINTS
#
class Waypoint(NamedPoint):  # same as fix
    """
    A Waypoint is a fix materialised by a VHF beacon of type navtype.
    """

    def __init__(self, ident: str, region: str, airport: str, lat: float, lon: float, navtype: str):
        # we may be should use navtype instead of "Waypoint" as point type
        NamedPoint.__init__(self, ident, region, airport, type(self).__name__, lat, lon)
        self.navtype = navtype


##########################
#
# S E G M E N T S
#
# AND COLLECION OF SEGMENTS
#
#
class AirwaySegment(Edge):
    """
    An AirwaySegment is a pair of NamedPoints, directed, with optional altitude information.
    """

    def __init__(self, names: str, start: NamedPoint, end: NamedPoint, direction: bool, lowhigh: int, fl_floor: int, fl_ceil: int):
        dist = distance(start, end)
        Edge.__init__(self, src=start, dst=end, directed=direction, weight=dist)
        self.names: List[str] = names.split("-")
        self.lowhigh = lowhigh
        self.fl_floor = fl_floor
        self.fl_ceil = fl_ceil

    def getKey(self):
        return key_path(self.start.id.replace(":", "-"), self.end.id.replace(":", "-"))

    def getInfo(self):
        return {
            "type": type(self).__name__,
            "start": self.start.id,
            "end": self.end.id,
            "names": self.names,
            "lowhigh": self.lowhigh,
            "fl_floor": self.fl_floor,
            "fl_ceil": self.fl_ceil,
            "length": self.weight,
            "directed": self.directed,
        }


class Airway(FeatureWithProps):
    """
    An Airway is a named array of AirwaySegments.
    It is exposed as a LineString.
    """

    def __init__(self, name: str, route: List[AirwaySegment]):
        self.name = name
        self.route = route
        arr = []
        via = ""
        first = None
        for s in self.route:
            if first is None:
                first = s
                arr.append(s.start)
            arr.append(s.end)
            via = via + "," + "-".join(s.names)
        FeatureWithProps.__init__(self, geometry=LineString(arr), properties={"name": name, "via": via})


##########################
#
# A I R   S P A C E
#
#
class Aerospace(Graph, ABC):
    """
    Airspace is a network of air routes.
    Vertices are airports, navaids, and fixes. Edges are airway segments.
    """

    def __init__(self, bbox=None, load_airways: bool = False):
        Graph.__init__(self)
        self.bbox = bbox
        self.load_airways = load_airways

        self.redis = None

        self.loaded = False
        self.airways_loaded = False

        self.airac_cycle: str | None = None

        self.airports_icao: Dict[str, "Airport"] = {}
        self.airports_iata: Dict[str, "Airport"] = {}
        self.holds: Dict[str, "Hold"] = {}
        self.airspaces: Dict[str, "ControlledAirspace"] = {}

    @classmethod
    def new(cls, load_airways: bool, cache: str, redis):
        airspace = None
        airspace_cache = os.path.join(cache, "aerospace.pickle")
        if os.path.exists(airspace_cache):
            logger.debug("loading aerospace from pickle..")
            with open(airspace_cache, "rb") as fp:
                airspace = pickle.load(fp)
            logger.debug("..done")
        else:
            logger.debug("creating aerospace..")
            airspace = cls(load_airways=load_airways)
            logger.debug("..loading aerospace..")
            ret = airspace.load(redis)
            if not ret[0]:
                logger.error("..aerospace **not loaded!**")
                return ret
            if load_airways:  # we only save the airspace if it contains everything
                logger.debug("..pickling aerospace..")
                with open(airspace_cache, "wb") as fp:
                    pickle.dump(airspace, fp)
            logger.debug("..done")
        return airspace

    def load(self, redis=None):
        if redis is not None and not self.load_airways:
            self.redis = redis
            return [True, "Airspace::load: Redis ready"]

        status = self.loadAirports()
        if not status[0]:
            return status

        status = self.loadNavaids()
        if not status[0]:
            return status

        status = self.loadFixes()
        if not status[0]:
            return status

        if self.load_airways:
            status = self.loadAirwaySegments()
            if not status[0]:
                return status

        status = self.loadAirspaces()
        if not status[0]:
            return status

        status = self.loadHolds()
        if not status[0]:
            return status

        return [True, f"Airspace loaded ({type(self).__name__})"]

    @abstractmethod
    def loadAirports(self):
        """
        Loads airports.
        """
        return [False, "no load implemented"]

    @abstractmethod
    def loadFixes(self, prefix: str = "earth"):
        """
        Loads fixes.
        """
        return [False, "no load implemented"]

    @abstractmethod
    def loadNavaids(self, prefix: str = "earth"):
        """
        Loads navaids.
        """
        return [False, "no load implemented"]

    @abstractmethod
    def loadAirwaySegments(self, prefix: str = "earth"):
        """
        Loads airway segments.
        """
        return [False, "no load implemented"]

    @abstractmethod
    def loadAirspaces(self):
        """
        Loads airspaces and their restrictions.
        """
        return [False, "no load implemented"]

    @abstractmethod
    def loadHolds(self, prefix: str = "earth"):
        """
        Loads holding points, their characteristics, and their restrictions.
        """
        return [False, "no load implemented"]

    def findHolds(self, name):
        """
        Finds holding positions with supplied name.

        :param      name:  The name
        :type       name:  { type_description }

        :returns:   { description_of_the_return_value }
        :rtype:     { return_type_description }
        """
        validholds = list(filter(lambda x: x.fix.id == name, self.holds.values()))
        return validholds

    def getAirportIATA(self, iata) -> Terminal | None:
        """
        Returns airport from airspace airport database with matching IATA code.

        :param      iata:  The iata
        :type       iata:  { type_description }
        """
        return self.airports_iata[iata] if iata in self.airports_iata.keys() else None

    def getAirportICAO(self, icao) -> Terminal | None:
        """
        Returns airport from airspace airport database with matching ICAO code.

        :param      iata:  The iata
        :type       iata:  { type_description }
        """
        return self.airports_icao[icao] if icao in self.airports_icao.keys() else None
