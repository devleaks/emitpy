"""
A succession of positions where the aircraft passes. Includes taxi and takeoff or landing and taxi.
"""
import logging
from functools import reduce
from typing import Union

from geojson import Point, LineString, Feature, FeatureCollection
from turfpy.measurement import distance

from ..flight import Flight
from ..airspace import Restriction
from ..airport import AirportBase
from ..aircraft import ACPERF
from ..geo import moveOn
from ..utils import FT

logger = logging.getLogger("Movement")


class MovePoint(Feature, Restriction):
    """
    A path point is a Feature with a Point geometry and mandatory properties for movements speed and altitude.
    THe name of the point is the synchronization name.
    """
    def __init__(self, geometry: Union[Point, LineString], properties: dict):
        Feature.__init__(self, geometry=geometry, properties={})
        Restriction.__init__(self)
        self._speed = 0
        self._vspeed = 0

    def getProp(self, propname: str):
        # Wrapper around Feature properties (inexistant in GeoJSON Feature)
        return self["properties"][propname] if propname in self["properties"] else None

    def setProp(self, name: str, value):
        # Wrapper around Feature properties (inexistant in GeoJSON Feature)
        self["properties"][name] = value

    def setAltitude(self, alt):
        if len(self["geometry"]["coordinates"]) > 2:
            self["geometry"]["coordinates"][2] = alt
        else:
            self["geometry"]["coordinates"].append(alt)

    def altitude(self):
        if len(self["geometry"]["coordinates"]) > 2:
            return self["geometry"]["coordinates"][2]
        else:
            return None

    def setSpeed(self, speed):
        self._speed = speed

    def speed(self):
        return self.speed

    def setVSpeed(self, vspeed):
        self._vspeed = vspeed

    def vspeed(self):
        return self._vspeed


class Movement:
    """
    Movement build the detailed path of the aircraft, both on the ground and in the air.
    """
    def __init__(self, flight: Flight, airport: AirportBase):
        self.flight = flight
        self.airport = airport
        self.moves = []  # Array of Features<Point>


    def asFeatureCollection(self):
        return FeatureCollection(features=self.moves)


    def asLineString(self):
        # reduce(lambda num1, num2: num1 * num2, my_numbers, 0)
        coords = reduce(lambda x, coords: coords + x["geometry"]["corrdinates"], self.moves, [])
        return LineString(coords)


    @staticmethod
    def cleanFeature(f):
        return Feature(geometry=f["geometry"], properties=f["properties"])


    @staticmethod
    def cleanFeatures(fa):
        c = []
        for f in fa:
            c.append(Movement.cleanFeature(f))
        return c


    @staticmethod
    def create(flight: Flight, airport: AirportBase):
        if type(flight).__name__ == "Arrival":
            return ArrivalPath(flight, airport)
        return DeparturePath(flight, airport)


    def mkPath(self):

        status = self.vnav()
        if not status[0]:
            logger.warning(status[1])
            return (False, status[1])

        status = self.lnav()
        if not status[0]:
            return (False, status[1])

        status = self.snav()
        if not status[0]:
            return (False, status[1])

        return (True, "Movement::mkPath done")


    def lnav(self):
        """
        Perform lateral navigation for route
        """
        # logger.debug(":lnav: ", len(self.vert_dict.keys()) - startLen, count)
        return (False, "Movement::lnav not implemented")


    def vnav(self):
        """
        Perform vertical navigation for route
        """
        return (False, "Movement::vnav not implemented")


    def snav(self):
        """
        Perform speed calculation, control, and adjustments for route
        """
        return (False, "Movement::snav not implemented")


class ArrivalPath(Movement):

    def __init__(self, flight: Flight, airport: AirportBase):
        Movement.__init__(self, flight=flight, airport=airport)


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
        #
        def moveOnCP(fc, fcidx, currpos, alt):
            p, i = moveOn(fc, fcidx, currpos, alt)
            return (MovePoint(geometry=p["geometry"], properties=p["properties"]), i)

        fc = self.flight.flightplan_cp
        ac = self.flight.aircraft
        actype = ac.actype

        actype.perfs()

        # PART 1: (FORWARD): From takeoff to top of ascent
        #
        #
        groundmv = 0
        fcidx = 0
        deptapt = fc[fcidx]
        alt = deptapt.altitude()
        if alt is None:
            logger.debug(":vnav: departure airport has no altitude: %s" % deptapt)
            alt = 0

        logger.debug(":vnav: departure airport: %s: %s, %d" % (type(deptapt).__name__, deptapt, alt))
        currpos = MovePoint(geometry=deptapt["geometry"], properties=deptapt["properties"])
        currpos.setProp("_mark", "departure")
        currpos.setSpeed(actype.getSI(ACPERF.takeoff_speed))
        ac.setPosition(currpos)

        self.moves.append(currpos)

        # initial climb, commonly accepted to above 1500ft AGL
        logger.debug(":vnav: initialClimb")
        step = actype.initialClimb(alt)  # (t, d, altend)
        # find initial climb point
        groundmv = groundmv + step[1]
        currpos, fcidx = moveOnCP(fc, fcidx, currpos, step[1])
        currpos.setAltitude(step[2])
        currpos.setSpeed(actype.getSI(ACPERF.initial_climb_speed))
        currpos.setVSpeed(actype.getSI(ACPERF.initial_climb_vspeed))
        currpos.setProp("_mark", "end_initial_climb")
        self.moves.append(currpos)

        logger.debug(":vnav: climbToFL100")
        step = actype.climbToFL100(currpos.altitude())  # (t, d, altend)
        groundmv = groundmv + step[1]
        currpos, fcidx = moveOnCP(fc, fcidx, currpos, step[1])
        currpos.setAltitude(step[2])
        currpos.setSpeed(actype.fl100Speed())
        currpos.setVSpeed(actype.getSI(ACPERF.climbFL150_vspeed))
        currpos.setProp("_mark", "end_fl100_climb")
        self.moves.append(currpos)

        # climb to cruise altitude
        cruise_speed = actype.getSI(ACPERF.cruise_mach)

        if self.flight.flight_level >= 150:
            logger.debug(":vnav: climbToFL150")
            step = actype.climbToFL240(currpos.altitude())  # (t, d, altend)
            groundmv = groundmv + step[1]
            currpos, fcidx = moveOnCP(fc, fcidx, currpos, step[1])
            currpos.setAltitude(step[2])
            currpos.setSpeed(actype.getSI(ACPERF.climbFL150_speed))
            currpos.setVSpeed(actype.getSI(ACPERF.climbFL150_vspeed))
            currpos.setProp("_mark", "end_fl150_climb")
            self.moves.append(currpos)

            if self.flight.flight_level >= 240:
                logger.debug(":vnav: climbToFL240")
                step = actype.climbToFL240(currpos.altitude())  # (t, d, altend)
                groundmv = groundmv + step[1]
                currpos, fcidx = moveOnCP(fc, fcidx, currpos, step[1])
                currpos.setAltitude(step[2])
                currpos.setSpeed(actype.getSI(ACPERF.climbFL240_speed))
                currpos.setVSpeed(actype.getSI(ACPERF.climbFL240_vspeed))
                currpos.setProp("_mark", "end_fl240_climb")
                self.moves.append(currpos)

                if self.flight.flight_level > 240:
                    logger.debug(":vnav: climbToCruise")
                    step = actype.climbToCruise(currpos.altitude(), self.flight.getCruiseAltitude())  # (t, d, altend)
                    groundmv = groundmv + step[1]
                    currpos, fcidx = moveOnCP(fc, fcidx, currpos, step[1])
                    currpos.setAltitude(step[2])
                    currpos.setSpeed(actype.getSI(ACPERF.climbmach_mach))
                    currpos.setVSpeed(actype.getSI(ACPERF.climbmach_vspeed))
                currpos.setProp("_mark", "top_of_ascent")
                self.moves.append(currpos)
                # cruise speed defaults to ACPERF.cruise_mach
            else:
                logger.debug(":vnav: climbToCruise below FL240")
                step = actype.climbToCruise(currpos.altitude(), self.flight.getCruiseAltitude())  # (t, d, altend)
                groundmv = groundmv + step[1]
                currpos, fcidx = moveOnCP(fc, fcidx, currpos, step[1])
                currpos.setAltitude(step[2])
                currpos.setSpeed(actype.getSI(ACPERF.climbFL240_speed))
                currpos.setVSpeed(actype.getSI(ACPERF.climbFL240_vspeed))
                currpos.setProp("_mark", "top_of_ascent")
                self.moves.append(currpos)
                cruise_speed = (actype.getSI(ACPERF.climbFL240_speed) + actype.getSI(ACPERF.cruise_mach))/ 2
                logger.warning(":vnav: cruise speed below FL240: %f m/s" % (cruise_speed))
        else:
            logger.debug(":vnav: climbToCruise below FL150")
            step = actype.climbToCruise(currpos.altitude(), self.flight.getCruiseAltitude())  # (t, d, altend)
            groundmv = groundmv + step[1]
            currpos, fcidx = moveOnCP(fc, fcidx, currpos, step[1])
            currpos.setAltitude(step[2])
            currpos.setSpeed(actype.getSI(ACPERF.climbFL240_speed))
            currpos.setVSpeed(actype.getSI(ACPERF.climbFL240_vspeed))
            currpos.setProp("_mark", "top_of_ascent")
            self.moves.append(currpos)
            logger.warning(":vnav: cruise speed below FL150: %f m/s" % (cruise_speed))
            cruise_speed = (actype.getSI(ACPERF.climbFL150_speed) + actype.getSI(ACPERF.cruise_mach))/ 2

        # accelerate to cruise speed smoothly
        acceldist = 5000  # we reach cruise speed after 5km horizontal flight
        logger.debug(":vnav: accelerate to cruise speed")
        currpos, fcidx = moveOnCP(fc, fcidx, currpos, acceldist)
        groundmv = groundmv + acceldist
        currpos.setAltitude(step[2])
        currpos.setSpeed(cruise_speed)
        currpos.setVSpeed(0)
        currpos.setProp("_mark", "reached_cruise_speed")
        self.moves.append(currpos)

        top_of_ascent_idx = fcidx  # we reach top of ascent between idx and idx+1
        cruise_start = currpos
        logger.debug(":vnav: cruise at %d after %f" % (top_of_ascent_idx, groundmv))
        logger.debug(":VNAV: ascent added (+%d %d)" % (len(self.moves), len(self.moves)))
        # cruise until top of descent

        # PART 2: (REVERSE): From brake on runway to top of descent
        #
        #
        tempmoves = []
        groundmv = 0
        fc = self.flight.flightplan_cp
        fc.reverse()
        fcidx = 0
        arrrwy = fc[fcidx]
        alt = arrrwy.altitude()
        if alt is None:
            logger.debug(":vnav: arrival runway has no altitude: %s" % arrrwy)
            alt = 0

        logger.debug(":vnav: arrival runway: %s: %s, %d" % (type(arrrwy).__name__, arrrwy, alt))
        currpos = MovePoint(geometry=arrrwy["geometry"], properties=arrrwy["properties"])
        currpos.setSpeed(actype.getSI(ACPERF.landing_speed))
        currpos.setProp("_mark", "runway_threshold")
        tempmoves.append(currpos)
        # we'll deal with what happens after the runway threshold in the lnav part.

        # we move to the final fix at max 3000ft, approach speed
        # initial climb, commonly accepted to above 1500ft AGL
        logger.debug(":vnav: final")
        step = actype.descentFinal(alt+(3000*FT), alt)  # (t, d, altend)
        groundmv = groundmv + step[1]
        # find initial climb point
        currpos, fcidx = moveOnCP(fc, fcidx, currpos, step[1])
        currpos.setAltitude(step[2])
        currpos.setSpeed(actype.getSI(ACPERF.approach_speed))
        currpos.setVSpeed(actype.getSI(ACPERF.approach_vspeed))
        currpos.setProp("_mark", "start_of_final")
        tempmoves.append(currpos)

        # go at 3000 AGL to last point of star

        # climb from  FL100 to FL240
        if self.flight.flight_level > 100:
            # climb from last point of star to FL100
            logger.debug(":vnav: end of descent")
            step = actype.descentApproach(10000*FT, alt+(3000*FT))  # (t, d, altend)
            groundmv = groundmv + step[1]
            # find initial climb point
            currpos, fcidx = moveOnCP(fc, fcidx, currpos, step[1])
            currpos.setAltitude(step[2])
            currpos.setSpeed(actype.getSI(ACPERF.approach_speed))
            currpos.setVSpeed(actype.getSI(ACPERF.approach_vspeed))
            currpos.setProp("_mark", "descent_fl100_reached")
            tempmoves.append(currpos)

            if self.flight.flight_level > 240:
                logger.debug(":vnav: descent to FL100")
                step = actype.descentToFL100(24000*FT)  # (t, d, altend)
                groundmv = groundmv + step[1]
                # find initial climb point
                currpos, fcidx = moveOnCP(fc, fcidx, currpos, step[1])
                currpos.setAltitude(step[2])
                currpos.setSpeed(actype.getSI(ACPERF.descentFL100_speed))
                currpos.setVSpeed(actype.getSI(ACPERF.descentFL100_vspeed))
                currpos.setProp("_mark", "descent_fl240_reached")
                tempmoves.append(currpos)

                # climb from  FL240 to cruise
                if self.flight.flight_level > 240:
                    logger.debug(":vnav: descent to FL240")
                    step = actype.descentToFL240(self.flight.getCruiseAltitude())  # (t, d, altend)
                    groundmv = groundmv + step[1]
                    # find initial climb point
                    currpos, fcidx = moveOnCP(fc, fcidx, currpos, step[1])
                    currpos.setAltitude(step[2])
                    currpos.setSpeed(actype.getSI(ACPERF.descentFL240_mach))
                    currpos.setVSpeed(actype.getSI(ACPERF.descentFL240_vspeed))
                    currpos.setProp("_mark", "top_of_descent")
                    tempmoves.append(currpos)
            else:
                logger.debug(":vnav: descent from under FL240")
                step = actype.descentToFL100(self.flight.getCruiseAltitude())  # (t, d, altend)
                groundmv = groundmv + step[1]
                # find initial climb point
                currpos, fcidx = moveOnCP(fc, fcidx, currpos, step[1])
                currpos.setAltitude(step[2])
                currpos.setSpeed(actype.getSI(ACPERF.initial_climb_speed))
                currpos.setVSpeed(actype.getSI(ACPERF.initial_climb_vspeed))
                currpos.setProp("_mark", "top_of_descent")  # !
                tempmoves.append(currpos)
        else:
            logger.debug(":vnav: descent from under FL100")
            step = actype.descentApproach(self.flight.getCruiseAltitude(), alt+(3000*FT))  # (t, d, altend)
            groundmv = groundmv + step[1]
            # find initial climb point
            currpos, fcidx = moveOnCP(fc, fcidx, currpos, step[1])
            currpos.setAltitude(step[2])
            currpos.setSpeed(actype.getSI(ACPERF.initial_climb_speed))
            currpos.setVSpeed(actype.getSI(ACPERF.initial_climb_vspeed))
            currpos.setProp("_mark", "top_of_descent")  # !
            tempmoves.append(currpos)

        # decelerate to descent speed smoothly
        acceldist = 5000  # we reach cruise speed after 5km horizontal flight
        logger.debug(":vnav: decelerate froms cruise speed")
        currpos, fcidx = moveOnCP(fc, fcidx, currpos, acceldist)
        groundmv = groundmv + acceldist
        currpos.setAltitude(self.flight.getCruiseAltitude())
        currpos.setSpeed(cruise_speed)  # computed when climbing
        currpos.setVSpeed(0)
        currpos.setProp("_mark", "end_of_cruise_speed")
        tempmoves.append(currpos)

        top_of_decent_idx = fcidx  # we reach top of ascent between idx and idx+1
        logger.debug(":vnav: cruise at %d after %f" % (top_of_decent_idx, groundmv))
        # cruise until top of descent

        # PART 3: Join top of ascent to top of descent at cruise speed
        #
        # We copy waypoints from start of cruise to end of cruise
        for i in range(top_of_ascent_idx, top_of_decent_idx):
            wpt = self.flight.flightplan_cp[i]
            p = MovePoint(geometry=wpt["geometry"], properties=wpt["properties"])
            p.setAltitude(self.flight.getCruiseAltitude())
            p.setSpeed(cruise_speed)
            self.moves.append(p)
        logger.debug(":VNAV: cruise added (+%d %d)" % (top_of_decent_idx-top_of_ascent_idx, len(self.moves)))

        # PART 4: Add descent and final
        #
        #
        tempmoves.reverse()
        self.moves = self.moves + tempmoves
        logger.debug(":VNAV: descent added (+%d %d)" % (len(tempmoves), len(self.moves)))

        print(FeatureCollection(features=Movement.cleanFeatures(self.moves)))

        return (True, "ArrivalPath::vnav completed without restriction")

    def snav(self):
        # ### SNAV: "Speed" nav for speed constraints not added through LNAV or VNAV.
        return (False, "ArrivalPath::vnav not implemented")


class DeparturePath(Movement):

    def __init__(self, flight: Flight, airport: AirportBase):
        Movement.__init__(self, flight=flight, airport=airport)


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
