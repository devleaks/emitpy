"""
A succession of positions where the aircraft passes.
"""
import logging
from functools import reduce

from geojson import Point, LineString, Feature, FeatureCollection

from ..flight import Flight
from ..airspace import Restriction

logger = logging.getLogger("Flight")


class PathPoint(Feature, Restriction):
    """
    A path point is a Feature with a Point geometry and mandatory properties for movements speed and altitude.
    THe name of the point is the synchronization name.
    """
    def __init__(self, name, lat: float, lon: float, alt: float = 0):
        Feature.__init__(self, geometry=Point((lon, lat, alt)), properties={})
        Restriction.__init__(self)
        self.name = name
        self._speed = 0

    def setSpeed(self, speed):
        self._speed = speed

    def speed(self):
        return self.speed

    def setAltitude(self, alt):
        self["geometry"]["coordinates"][2] = alt

    def altitude(self):
        return self["geometry"]["coordinates"][2]


class AircraftPath:
    """
    AircraftPath build the detailed path of the aircraft, both on the ground and in the air.
    """
    def __init__(self, flight: Flight):
        self.flight = flight
        self.route = []  # Array of Features<Point>


    def asFeatureCollection(self):
        return FeatureCollection(features=self.route)


    def asLineString(self):
        # reduce(lambda num1, num2: num1 * num2, my_numbers, 0)
        coords = reduce(lambda x, coords: coords + x["geometry"]["corrdinates"], self.route, [])
        return LineString(coords)


    @staticmethod
    def cleanFeatures(fa):
        c = []
        for f in fa:
            c.append(Feature(geometry=f["geometry"], properties=f["properties"]))
        return c


    def mkPath(self):

        status = self.lnav()
        if not status[0]:
            logger.warning(status[1])
            return (False, status[1])

        status = self.lnav()
        if not status[0]:
            return (False, status[1])

        status = self.lnav()
        if not status[0]:
            return (False, status[1])

        return (True, "AircraftPath::mkPath done")


    def lnav(self):
        """
        Perform lateral navigation for route
        """
        # logging.debug("AircraftPath::lnav: ", len(self.vert_dict.keys()) - startLen, count)
        return (False, "AircraftPath::lnav not implemented")


    def vnav(self):
        """
        Perform vertical navigation for route
        """
        return (False, "AircraftPath::vnav not implemented")


    def snav(self):
        """
        Perform speed calculation, control, and adjustments for route
        """
        return (False, "AircraftPath::snav not implemented")


class ArrivalPath(AircraftPath):

    def __init__(self, flight: "Flight"):
        AircraftPath.__init__(self, flight=flight)


    def lnav(self):
        # ### LNAV
        # Start from flight path with departure airport and route to destination.
        # Set arrival runway
        # Select STAR
        # Add STAR
        # Add optional hold
        # Add transition from cruise to STAR. We may need to backtrack on cruise waypoint to find where to transition from cruise to STAR.
        # Add Approach
        # Ensure FIX
        # Add touchdown
        # Determine exit runway from aircraft type, weather. First is RE:34L:0 and last is RE:34L:L.
        # Roll to exit
        # Find closest point on taxiway network.
        # Join exit runway to closest point on taxiway network.
        # Find parking's closest point on taxiway network.
        # Route on taxiway from runway exit to parking's closest point on taxiway network.
        # Join parking's closest point on taxiway network to parking.
        # ON BLOCK
        return (False, "ArrivalPath::lnav not implemented")

    def vnav(self):
        # ### VNAV
        # Start at departure airport AGL.
        # Determine cruise FL from total flight distance (0-300: 200, 0-600: FL 250, 600+: FL300)
        # From aircraft, average climb lat and v speeds, determine FL100 reach.
        #
        # (WE WILL LATER ADD SAME ALT POINT ON LOW ROUTE / HIGH ROUTE JUNCTION + TRANSITION AROUND FL 180)
        #
        # Add interpolated FL100 reach with alt/speed requirement.
        # From aircraft, average climb lat and v speeds, determine distance to climb to FL cruise (i.e. top-of-climb).
        # Add interpolated top-of-climb with alt/speed requirement

        # From cruize FL and and first point with alt requirements on descent/STAR: Determine top-of-descent.
        # Add interpolated top-of-descent.
        # Fly cruise from top-of-climb to top-of-descent.
        # Descent to first waypoint with alt requirements on descent/STAR
        # Follow STAR
        # Follow APPROACH (simplifies METAR Hpa, MSL, AGL)
        # Follow FINAL
        # Touch down.
        return (False, "ArrivalPath::vnav not implemented")

    def snav(self):
        # ### SNAV: "Speed" nav for speed constraints not added through LNAV or VNAV.
        return (False, "ArrivalPath::snav not implemented")


class DeparturePath(AircraftPath):

    def __init__(self, flight: Flight):
        AircraftPath.__init__(self, flight=flight)


    def lnav(self):
        # ### LNAV
        # Determine closest point from parking to taxiway network.
        # OFFBLOCK
        # Pushback on that segment (in straight line)
        # Determine departure runway, runway entry (runway hold).
        # Determine closest point from runway entry to taxiway netowrk.
        # Route on taxiway between closest point to parking to closest point to runway entry.
        # From runway hold, backtrack interpolate N positions for N taxi holds (N=0~10)
        # Go to take-off hold
        # Accelerate to take-off point (now fixed, mobile later)
        # Initial climb to initial climb fix.
        # Go to start of SID (straight line)
        # Follow SID
        # Determine start of cruise from last point of SID.
        # Transition to start of cruise
        # Cruise
        return (False, "DeparturePath::lnav not implemented")


    def vnav(self):
        # ### VNAV
        # Start at airport AGL.
        # Determine cruise FL from total flight distance (0-300: 200, 0-600: FL 250, 600+: FL300)
        # Climb to initial fix
        # From aircraft, average climb lat and v speeds, determine FL100 reach.
        # Climb to waypoint restrictions to FL100 and/or end of SID
        # From aircraft, average climb lat and v speeds, determine cruise level reach.
        # Climb to cruise level.
        # From aircraft, average descent lat and v speeds, determine FL100 reach.
        # Place and interpolate FL100 point.
        # Descent aicraft at average descent speed to airport GL.
        return (False, "DeparturePath::vnav not implemented")

    def snav(self):
        # ### SNAV: "Speed" nav for speed constraints not added through LNAV or VNAV.
        return (False, "DeparturePath::snav not implemented")







