"""
A succession of positions where the aircraft passes. Includes taxi and takeoff or landing and taxi.
"""
import logging
from math import pi
from typing import Union
import copy

from geojson import Point, LineString, Feature, FeatureCollection
from turfpy.measurement import distance, destination, bearing

from ..flight import Flight
from ..airspace import Restriction
from ..airport import AirportBase
from ..aircraft import ACPERF
from ..geo import moveOn
from ..utils import FT

from .standardturn import standard_turn_flyby

logger = logging.getLogger("Movement")

TAXI_SPEED = 10  # 10m/s = 36km/h = taxi speed
SLOW_SPEED = 1.4 # 1.4m/s = 5km/h = slow speed


class MovePoint(Feature, Restriction):
    """
    A path point is a Feature with a Point geometry and mandatory properties for movements speed and altitude.
    THe name of the point is the synchronization name.
    """
    def __init__(self, geometry: Union[Point, LineString], properties: dict):
        Feature.__init__(self, geometry=geometry, properties=copy.deepcopy(properties))
        Restriction.__init__(self)
        self._speed = None
        self._vspeed = None

    def getProp(self, propname: str):
        # Wrapper around Feature properties (inexistant in GeoJSON Feature)
        return self["properties"][propname] if propname in self["properties"] else "None"

    def setProp(self, name: str, value):
        # Wrapper around Feature properties (inexistant in GeoJSON Feature)
        self["properties"][name] = value

    def setColor(self, color: str):
        # geojson.io specific
        self["properties"]["marker-color"] = color
        self["properties"]["marker-size"] = "medium"
        self["properties"]["marker-symbol"] = ""

    def setAltitude(self, alt):
        if len(self["geometry"]["coordinates"]) > 2:
            self["geometry"]["coordinates"][2] = alt
        else:
            self["geometry"]["coordinates"].append(alt)
        self["properties"]["altitude"] = alt

    def altitude(self):
        if len(self["geometry"]["coordinates"]) > 2:
            return self["geometry"]["coordinates"][2]
        else:
            return None

    def setSpeed(self, speed):
        self._speed = speed
        self["properties"]["speed"] = speed

    def speed(self):
        return self._speed

    def setVSpeed(self, vspeed):
        self._vspeed = vspeed
        self["properties"]["vspeed"] = vspeed

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
        self.moves_st = []  # Array of Features<Point>
        self.takeoff_hold = None
        self.end_rollout = None
        self.holdingpoint = None
        self.taxi = []  # Array of Features<Point>


    def asFeatureCollection(self):
        return FeatureCollection(features=self.moves)


    def asLineString(self):
        # reduce(lambda num1, num2: num1 * num2, my_numbers, 0)
        coords = []
        for x in self.moves:
            # logger.debug(":asLineString: %d %s %s %s" % (len(coords), x.getProp("fpidx"), x.getProp("_mark"), x.getProp("_plan_segment_type")))
            coords.append(x["geometry"]["coordinates"])
        # coords = reduce(lambda x, coords: coords + x["geometry"]["coordinates"], self.moves, [])
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


    def make(self):

        status = self.vnav()
        if not status[0]:
            logger.warning(status[1])
            return status

        status = self.standard_turns()
        if not status[0]:
            logger.warning(status[1])
            return status

        status = self.interpolate()
        if not status[0]:
            logger.warning(status[1])
            return status

        fc = Movement.cleanFeatures(self.moves_st)
        fc.append(Feature(geometry=self.asLineString()))
        print(FeatureCollection(features=fc))

        status = self.lnav()
        if not status[0]:
            logger.warning(status[1])
            return status

        return (True, "Movement::make completed")


    def interpolate(self):

        to_interp = self.moves_st if self.moves_st is not None else self.moves

        def interpolate_speed(istart, iend):
            speedstart = to_interp[istart].speed()  # first known speed
            speedend = to_interp[iend].speed()  # last known speed

            if speedstart == speedend:  # simply copy
                for idx in range(istart, iend):
                    to_interp[idx].setSpeed(speedstart)
                return

            ratios = {}
            spdcumul = 0
            for idx in range(istart+1, iend):
                d = distance(to_interp[idx-1], to_interp[idx], "m")
                spdcumul = spdcumul + d
                ratios[idx] = spdcumul
            # logger.debug(":interpolate_speed: (%d)%f -> (%d)%f, %f" % (istart, speedstart, iend, speedend, spdcumul))
            speed_a = (speedend - speedstart) / spdcumul
            speed_b = speedstart
            for idx in range(istart+1, iend):
                # logger.debug(":interpolate_speed: %d %f %f" % (idx, ratios[idx]/spdcumul, speed_b + speed_a * ratios[idx]))
                to_interp[idx].setSpeed(speed_b + speed_a * ratios[idx] / spdcumul)

        def interpolate_altitude(istart, iend):
            altstart = to_interp[istart].altitude()  # first known alt
            altend = to_interp[iend].altitude()  # last known alt

            if altstart == altend:  # simply copy
                for idx in range(istart, iend):
                    to_interp[idx].setAltitude(altstart)
                return

            ratios = {}
            altcumul = 0
            for idx in range(istart+1, iend+1):
                d = distance(to_interp[idx-1], to_interp[idx], "m")
                altcumul = altcumul + d
                ratios[idx] = altcumul
            # logger.debug(":interpolate_alt: (%d)%f -> (%d)%f, %f" % (istart, altstart, iend, altend, altcumul))
            alt_a = (altend - altstart) / altcumul
            alt_b = altstart
            for idx in range(istart+1, iend):
                # logger.debug(":interpolate_alt: %d %f %f" % (idx, ratios[idx]/altcumul, alt_b + alt_a * ratios[idx]))
                to_interp[idx].setAltitude(alt_b + alt_a * ratios[idx] / altcumul)

        # we do have a speed for first point in flight for both arrival (takeoff_speed, apt.alt) and departure (landing_speed, apt.alt)
        nospeed_idx = None  # index of last elem with not speed, elem[0] has speed.
        noalt_idx = None
        for idx in range(1, len(to_interp)):
            f = to_interp[idx]

            s = f.speed()
            if s is None:
                if nospeed_idx is None:
                    nospeed_idx = idx - 1
            else:
                if nospeed_idx is not None:
                    interpolate_speed(nospeed_idx, idx)
                    nospeed_idx = None

            a = f.altitude()
            if a is None:
                if noalt_idx is None:
                    noalt_idx = idx - 1
            else:
                if noalt_idx is not None:
                    interpolate_altitude(noalt_idx, idx)
                    noalt_idx = None

        # i = 0
        # for f in self.moves:
        #     s = f.speed()
        #     a = f.altitude()
        #     logger.debug(":vnav: alter: %d: %f %f" % (i, s if s is not None else -1, a if a is not None else -1))
        #     i = i + 1

        return (True, "Movement::interpolated speed and altitude")


    def standard_turns(self):
        def turnRadius(speed):  # speed in m/s, returns radius in m
            return 120 * speed / (2 * pi)

        self.moves_st = []
        last_speed = 100
        self.moves_st.append(self.moves[0])

        for i in range(1, len(self.moves) - 1):
            li = LineString([self.moves[i-1]["geometry"]["coordinates"], self.moves[i]["geometry"]["coordinates"]])
            lo = LineString([self.moves[i]["geometry"]["coordinates"], self.moves[i+1]["geometry"]["coordinates"]])
            s = last_speed  # arrin[i].speed()
            if s is None:
                s = last_speed
            arc = standard_turn_flyby(li, lo, turnRadius(s))
            last_speed = s

            if arc is not None:
                self.moves_st.append(self.moves[i])
                for p in arc:
                    self.moves_st.append(MovePoint(geometry=p["geometry"], properties=p["properties"]))
            else:
                self.moves_st.append(self.moves[i])
        return (True, "Movement::standard_turns added")


    def vnav(self):
        """
        Perform vertical navigation for route
        @todo: Add optional hold
        """

        def moveOnCP(fc, fcidx, currpos, alt):
            p, i = moveOn(fc, fcidx, currpos, alt)
            return (MovePoint(geometry=p["geometry"], properties=p["properties"]), i)

        def addCurrentPoint(coll, pos, oi, ni, reverse: bool = False):
            # logger.debug(":addCurrentPoint: %d %d %s" % (oi, ni, reverse))
            if oi != ni:
                for idx in range(oi+1, ni+1):
                    i = idx if not reverse else len(self.flight.flightplan_cp) - idx - 1
                    wpt = self.flight.flightplan_cp[i]
                    p = MovePoint(geometry=wpt["geometry"], properties=wpt["properties"])
                    currpos.setProp("fpidx", i)
                    p.setColor("#ff0000") # flight plan point in RED
                    #@todo: will need to interpolate alt and speed for these points
                    coll.append(p)
                    # logger.debug(":addCurrentPoint: adding flight plan point: %d %s (%d)" % (i, wpt.getProp("_plan_segment_type"), len(coll)))
            pos.setColor("#00ff00")  # remarkable point in FREEN
            coll.append(pos)
            # logger.debug(":addCurrentPoint: adding remarkable point: %s (%d)" % (pos.getProp("_mark"), len(coll)))
            return ni

        fc = self.flight.flightplan_cp
        ac = self.flight.aircraft
        actype = ac.actype
        # actype.perfs()
        logger.debug(":vnav: %s: %d points in flight plan" % (type(self).__name__, len(fc)))

        # for f in self.flight.flightplan_cp:
        #     logger.debug(":vnav: flight plan: %s" % (f.getProp("_plan_segment_type")))

        # PART 1: (FORWARD): From takeoff to top of ascent
        #
        #
        logger.debug("DEPARTURE **********")
        groundmv = 0
        fcidx = 0

        if type(self).__name__ == "DeparturePath":  # take off
            TOH_BLASTOFF = 0.2  # km
            rwy = self.flight.runway
            rwy_threshold = rwy.getPoint()
            alt = rwy_threshold.altitude()
            if alt is None:
                logger.warning(":vnav: departure airport has no altitude: %s" % rwy_threshold)
                alt = 0

            brg = bearing(rwy_threshold, rwy.end.getPoint())
            takeoff_hold = destination(rwy_threshold, TOH_BLASTOFF, brg, {"units": "km"})
            logger.debug(":vnav: departure from %s, %f" % (rwy.name, brg))

            currpos = MovePoint(geometry=takeoff_hold["geometry"], properties={})
            currpos.setAltitude(alt)
            currpos.setSpeed(actype.getSI(0))
            currpos.setVSpeed(0)
            currpos.setColor("#880088")  # takeoff
            currpos.setProp("_mark", "takeoff_hold")
            currpos.setProp("fpidx", 0)
            self.moves.append(currpos)
            self.takeoff_hold = copy.deepcopy(currpos)  # we keep this special position for taxiing (end_of_taxi)
            logger.debug(":vnav: takeoff hold at %s, %f" % (rwy.name, TOH_BLASTOFF))

            takeoff_distance = actype.getSI(ACPERF.takeoff_distance) * self.airport.runwayIsWet() / 1000  # must be km for destination()
            takeoff = destination(takeoff_hold, takeoff_distance, brg, {"units": "km"})

            currpos = MovePoint(geometry=takeoff["geometry"], properties={})
            currpos.setAltitude(alt)
            currpos.setSpeed(actype.getSI(ACPERF.takeoff_speed))
            currpos.setVSpeed(actype.getSI(ACPERF.initial_climb_speed))
            currpos.setColor("#880088")  # takeoff
            currpos.setProp("_mark", "takeoff")
            currpos.setProp("fpidx", 0)
            self.moves.append(currpos)
            groundmv = takeoff_distance
            logger.debug(":vnav: takeoff at %s, %f" % (rwy.name, takeoff_distance))

            # initial climb, commonly accepted to above 1500ft AGL
            logger.debug(":vnav: initialClimb")
            step = actype.initialClimb(alt)  # (t, d, altend)
            initial_climb_distance = step[1] / 1000  # km
            # find initial climb point

            # we climb on path to see if we reach indices...
            currpos, newidx = moveOnCP(fc, fcidx, currpos, initial_climb_distance)

            # we ignore currpos for now, we will climb straight...
            initial_climb = destination(takeoff, initial_climb_distance, brg, {"units": "km"})
            currpos = MovePoint(geometry=initial_climb["geometry"], properties={})
            currpos.setAltitude(alt)
            currpos.setSpeed(actype.getSI(ACPERF.initial_climb_speed))
            currpos.setVSpeed(actype.getSI(ACPERF.initial_climb_vspeed))
            currpos.setColor("#880088")  # takeoff
            currpos.setProp("_mark", "end_initial_climb")
            currpos.setProp("fpidx", newidx)
            self.moves.append(currpos)
            logger.debug(":vnav: initial climb end at %d, %f" % (newidx, initial_climb_distance))
            fcidx = newidx
            groundmv = groundmv + initial_climb_distance

        else:  # ArrivalPath, simpler departure
            # Someday, we could add SID departure from runway for remote airport as well
            # Get METAR at airport, determine runway, select random runway & SID
            deptapt = fc[0]
            alt = deptapt.altitude()
            if alt is None:
                logger.warning(":vnav: departure airport has no altitude: %s" % deptapt)
                alt = 0
            currpos = MovePoint(geometry=deptapt["geometry"], properties=deptapt["properties"])
            currpos.setProp("_mark", "origin")
            currpos.setSpeed(actype.getSI(ACPERF.takeoff_speed))
            currpos.setColor("#ffff00")  # departure airport in YELLOW
            currpos.setProp("fpidx", fcidx)
            self.moves.append(currpos)
            logger.debug(":vnav: origin added first point")

            # initial climb, commonly accepted to above 1500ft AGL
            logger.debug(":vnav: initialClimb")
            step = actype.initialClimb(alt)  # (t, d, altend)
            # find initial climb point
            groundmv = step[1]
            currpos, newidx = moveOnCP(fc, fcidx, currpos, step[1])
            currpos.setAltitude(step[2])
            currpos.setSpeed(actype.getSI(ACPERF.initial_climb_speed))
            currpos.setVSpeed(actype.getSI(ACPERF.initial_climb_vspeed))
            currpos.setProp("_mark", "end_initial_climb")
            fcidx = addCurrentPoint(self.moves, currpos, fcidx, newidx)

        logger.debug(":vnav: climbToFL100")
        step = actype.climbToFL100(currpos.altitude())  # (t, d, altend)
        groundmv = groundmv + step[1]
        currpos, newidx = moveOnCP(fc, fcidx, currpos, step[1])
        currpos.setAltitude(step[2])
        currpos.setSpeed(actype.fl100Speed())
        currpos.setVSpeed(actype.getSI(ACPERF.climbFL150_vspeed))
        currpos.setProp("_mark", "end_fl100_climb")
        fcidx = addCurrentPoint(self.moves, currpos, fcidx, newidx)

        # climb to cruise altitude
        cruise_speed = actype.getSI(ACPERF.cruise_mach)

        if self.flight.flight_level >= 150:
            logger.debug(":vnav: climbToFL150")
            step = actype.climbToFL240(currpos.altitude())  # (t, d, altend)
            groundmv = groundmv + step[1]
            currpos, newidx = moveOnCP(fc, fcidx, currpos, step[1])
            currpos.setAltitude(step[2])
            currpos.setSpeed(actype.getSI(ACPERF.climbFL150_speed))
            currpos.setVSpeed(actype.getSI(ACPERF.climbFL150_vspeed))
            currpos.setProp("_mark", "end_fl150_climb")
            fcidx = addCurrentPoint(self.moves, currpos, fcidx, newidx)

            if self.flight.flight_level >= 240:
                logger.debug(":vnav: climbToFL240")
                step = actype.climbToFL240(currpos.altitude())  # (t, d, altend)
                groundmv = groundmv + step[1]
                currpos, newidx = moveOnCP(fc, fcidx, currpos, step[1])
                currpos.setAltitude(step[2])
                currpos.setSpeed(actype.getSI(ACPERF.climbFL240_speed))
                currpos.setVSpeed(actype.getSI(ACPERF.climbFL240_vspeed))
                currpos.setProp("_mark", "end_fl240_climb")
                fcidx = addCurrentPoint(self.moves, currpos, fcidx, newidx)

                if self.flight.flight_level > 240:
                    logger.debug(":vnav: climbToCruise")
                    step = actype.climbToCruise(currpos.altitude(), self.flight.getCruiseAltitude())  # (t, d, altend)
                    groundmv = groundmv + step[1]
                    currpos, newidx = moveOnCP(fc, fcidx, currpos, step[1])
                    currpos.setAltitude(step[2])
                    currpos.setSpeed(actype.getSI(ACPERF.climbmach_mach))
                    currpos.setVSpeed(actype.getSI(ACPERF.climbmach_vspeed))
                    currpos.setProp("_mark", "top_of_ascent")
                    fcidx = addCurrentPoint(self.moves, currpos, fcidx, newidx)
                    # cruise speed defaults to ACPERF.cruise_mach, we don't need to specify it
            else:
                logger.debug(":vnav: climbToCruise below FL240")
                step = actype.climbToCruise(currpos.altitude(), self.flight.getCruiseAltitude())  # (t, d, altend)
                groundmv = groundmv + step[1]
                currpos, newidx = moveOnCP(fc, fcidx, currpos, step[1])
                currpos.setAltitude(step[2])
                currpos.setSpeed(actype.getSI(ACPERF.climbFL240_speed))
                currpos.setVSpeed(actype.getSI(ACPERF.climbFL240_vspeed))
                currpos.setProp("_mark", "top_of_ascent")
                fcidx = addCurrentPoint(self.moves, currpos, fcidx, newidx)
                cruise_speed = (actype.getSI(ACPERF.climbFL240_speed) + actype.getSI(ACPERF.cruise_mach))/ 2
                logger.warning(":vnav: cruise speed below FL240: %f m/s" % (cruise_speed))
        else:
            logger.debug(":vnav: climbToCruise below FL150")
            step = actype.climbToCruise(currpos.altitude(), self.flight.getCruiseAltitude())  # (t, d, altend)
            groundmv = groundmv + step[1]
            currpos, newidx = moveOnCP(fc, fcidx, currpos, step[1])
            currpos.setAltitude(step[2])
            currpos.setSpeed(actype.getSI(ACPERF.climbFL240_speed))
            currpos.setVSpeed(actype.getSI(ACPERF.climbFL240_vspeed))
            currpos.setProp("_mark", "top_of_ascent")
            fcidx = addCurrentPoint(self.moves, currpos, fcidx, newidx)
            logger.warning(":vnav: cruise speed below FL150: %f m/s" % (cruise_speed))
            cruise_speed = (actype.getSI(ACPERF.climbFL150_speed) + actype.getSI(ACPERF.cruise_mach))/ 2

        # accelerate to cruise speed smoothly
        acceldist = 5000  # we reach cruise speed after 5km horizontal flight
        logger.debug(":vnav: accelerate to cruise speed")
        currpos, newidx = moveOnCP(fc, fcidx, currpos, acceldist)
        groundmv = groundmv + acceldist
        currpos.setAltitude(step[2])
        currpos.setSpeed(cruise_speed)
        currpos.setVSpeed(0)
        currpos.setProp("_mark", "reached_cruise_speed")
        fcidx = addCurrentPoint(self.moves, currpos, fcidx, newidx)

        top_of_ascent_idx = fcidx + 1 # we reach top of ascent between idx and idx+1, so we cruise from idx+1 on.
        logger.debug(":vnav: cruise at %d after %f" % (top_of_ascent_idx, groundmv))
        logger.debug(":vnav: ascent added (+%d %d)" % (len(self.moves), len(self.moves)))
        # cruise until top of descent

        # PART 2: (REVERSE): From brake on runway to top of descent
        #
        #
        logger.debug("ARRIVAL **********")
        FINAL_ALT = 1000*FT
        APPROACH_ALT = 3000*FT
        STAR_ALT = 6000*FT

        revmoves = []
        groundmv = 0
        fc = self.flight.flightplan_cp.copy()
        fc.reverse()
        fcidx = 0

        # for f in fc:
        #     logger.debug(":vnav: flight plan reversed: %s" % (f.getProp("_plan_segment_type")))

        if type(self).__name__ == "ArrivalPath":  # the path starts at the END of the departure runway
            LAND_TOUCH_DOWN = 0.4  # km
            rwy = self.flight.runway
            rwy_threshold = rwy.getPoint()
            alt = rwy_threshold.altitude()
            if alt is None:
                logger.warning(":vnav: departure airport has no altitude: %s" % rwy_threshold)
                alt = 0

            brg = bearing(rwy_threshold, rwy.end.getPoint())
            touch_down = destination(rwy_threshold, LAND_TOUCH_DOWN, brg, {"units": "km"})
            logger.debug(":vnav: arrival runway %s, %f" % (rwy.name, brg))

            # First point is where stopped
            rollout_distance = actype.getSI(ACPERF.landing_distance) * self.airport.runwayIsWet() / 1000 # must be km for destination()
            landing = destination(touch_down, rollout_distance, brg, {"units": "km"})

            currpos = MovePoint(geometry=landing["geometry"], properties={})
            currpos.setAltitude(alt)
            currpos.setSpeed(TAXI_SPEED)
            currpos.setVSpeed(0)
            currpos.setColor("#880088")  # takeoff
            currpos.setProp("_mark", "end_rollout")
            currpos.setProp("fpidx", 0)
            revmoves.append(currpos)
            logger.debug(":vnav: stopped at %s, %f" % (rwy.name, rollout_distance))
            self.end_rollout = copy.deepcopy(currpos)  # we keep this special position for taxiing (start_of_taxi)

            # Point before is touch down
            currpos = MovePoint(geometry=touch_down["geometry"], properties={})
            currpos.setAltitude(alt)
            currpos.setSpeed(actype.getSI(ACPERF.landing_speed))
            currpos.setVSpeed(0)
            currpos.setColor("#880088")  # takeoff
            currpos.setProp("_mark", "touch_down")
            currpos.setProp("fpidx", 0)
            revmoves.append(currpos)
            logger.debug(":vnav: touch down at %s, %f" % (rwy.name, LAND_TOUCH_DOWN))

        else:
            # Someday, we could add STAR/APPCH to runway for remote airport as well
            # Get METAR at airport, determine runway, select random RWY, STAR and APPCH
            arrvapt = fc[fcidx]
            alt = arrvapt.altitude()
            if alt is None:
                logger.warning(":vnav: arrival airport has no altitude: %s" % arrvapt)
                alt = 0

            currpos = MovePoint(geometry=arrvapt["geometry"], properties=arrvapt["properties"])
            currpos.setProp("_mark", "destination")
            currpos.setSpeed(actype.getSI(ACPERF.landing_speed))
            currpos.setProp("fpidx", len(fc) - fcidx)
            currpos.setColor("#00ffff")  # Arrival airport in CYAN
            revmoves.append(currpos)
            logger.debug(":vnav: destination added last point")

        # we move to the final fix at max 3000ft, approach speed
        logger.debug(":vnav: final")
        step = actype.descentFinal(alt+APPROACH_ALT, alt)  # (t, d, altend)
        groundmv = groundmv + step[1]
        # find initial climb point
        currpos, newidx = moveOnCP(fc, fcidx, currpos, step[1])
        currpos.setAltitude(alt+APPROACH_ALT)
        currpos.setSpeed(actype.getSI(ACPERF.landing_speed))  # approach speed?
        currpos.setVSpeed(actype.getSI(ACPERF.approach_vspeed))
        currpos.setProp("_mark", "start_of_final")
        currpos.setProp("fpidx", fcidx)
        fcidx = addCurrentPoint(revmoves, currpos, fcidx, newidx, True)


        # i = 0
        # for f in fc:
        #     logger.debug(":vnav: flight plan last at %d %s" % (i, f.id))
        #     # logger.debug(":vnav: revmoves at %d %s" % (i, f))
        #     i = i + 1

        # go at APPROACH_ALT at first point of approach / last point of star
        if type(self).__name__ == "ArrivalPath":

            # find first point of approach:
            k = len(fc) - 1
            while fc[k].getProp("_plan_segment_type") != "appch" and k > 0:
                k = k - 1
            if k == 0:
                logger.warning(":vnav: no approach found")
            else:
                logger.debug(":vnav: start of approach at index %d, %s" % (k, fc[k].getProp("_plan_segment_type")))
                if k <= fcidx:
                    logger.debug(":vnav: final fix seems further away than start of apprach")
                else:
                    logger.debug(":vnav: flight level to final fix")
                    # add all approach points between start to approach to final fix
                    for i in range(fcidx+1, k):
                        wpt = fc[i]
                        # logger.debug(":vnav: APPCH: flight level: %d %s" % (i, wpt.getProp("_plan_segment_type")))
                        p = MovePoint(geometry=wpt["geometry"], properties=wpt["properties"])
                        p.setAltitude(alt+APPROACH_ALT)
                        p.setSpeed(actype.getSI(ACPERF.approach_speed))
                        p.setVSpeed(0)
                        p.setColor("#ff00ff")  # approach in MAGENTA
                        p.setProp("_mark", "approach")
                        p.setProp("fpidx", i)
                        revmoves.append(p)
                        # logger.debug(":vnav: adding remarkable point: %d %s (%d)" % (i, p.getProp("_mark"), len(revmoves)))

                    # i = 0
                    # for f in revmoves:
                    #     a = f.altitude()
                    #     s = f.speed()
                    #     logger.debug(":vnav: revmoves before last at %d %s %s: %f %f" % (i, f.getProp("_mark"), f.getProp("_plan_segment_type"), s if s is not None else -1, a if a is not None else -1))
                    #     # logger.debug(":vnav: revmoves at %d %s" % (i, f))
                    #     i = i + 1

                    # add start of approach
                    currpos = MovePoint(geometry=fc[k]["geometry"], properties=fc[k]["properties"])
                    currpos.setAltitude(alt+APPROACH_ALT)
                    currpos.setSpeed(actype.getSI(ACPERF.approach_speed))
                    currpos.setVSpeed(0)
                    currpos.setProp("_mark", "start_of_approach")
                    currpos.setProp("fpidx", k)
                    currpos.setColor("#880088")  # approach in MAGENTA
                    revmoves.append(currpos)
                    # logger.debug(":vnav: adding remarkable point: %d %s (%d)" % (k, currpos.getProp("_mark"), len(revmoves)))

                    fcidx = k

                    # i = 0
                    # for f in revmoves:
                    #     a = f.altitude()
                    #     s = f.speed()
                    #     logger.debug(":vnav: revmoves at %d %s %s: %f %f" % (i, f.getProp("_mark"), f.getProp("_plan_segment_type"), s if s is not None else -1, a if a is not None else -1))
                    #     # logger.debug(":vnav: revmoves at %d %s" % (i, f))
                    #     i = i + 1

            # find first point of star:
            k = len(fc) - 1
            while fc[k].getProp("_plan_segment_type") != "star" and k > 0:
                k = k - 1
            if k == 0:
                logger.warning(":vnav: no star found")
            else:
                logger.debug(":vnav: start of star at index %d, %s" % (k, fc[k].getProp("_plan_segment_type")))
                if k <= fcidx:
                    logger.debug(":vnav: final fix seems further away than start of star")
                else:
                    logger.debug(":vnav: flight level to start of approach")
                    # add all approach points between start to approach to final fix
                    for i in range(fcidx+1, k):
                        wpt = fc[i]
                        # logger.debug(":vnav: STAR: flight level: %d %s" % (i, wpt.getProp("_plan_segment_type")))
                        p = MovePoint(geometry=wpt["geometry"], properties=wpt["properties"])
                        p.setAltitude(alt+STAR_ALT)
                        p.setSpeed(actype.getSI(ACPERF.approach_speed))
                        p.setVSpeed(0)
                        p.setColor("#ff00ff")  # star in MAGENTA
                        p.setProp("_mark", "star")
                        p.setProp("fpidx", i)
                        revmoves.append(p)
                        # logger.debug(":vnav: adding remarkable point: %d %s (%d)" % (i, p.getProp("_mark"), len(revmoves)))
                    # add start of approach
                    #
                    # @todo:
                    # we assume start of star is where holding occurs
                    # Add holding pattern
                    self.holdingpoint = fc[k].id
                    logger.debug(":vnav: holding at : %s" % (self.holdingpoint))
                    currpos = MovePoint(geometry=fc[k]["geometry"], properties=fc[k]["properties"])
                    currpos.setAltitude(alt+STAR_ALT)
                    currpos.setSpeed(actype.getSI(ACPERF.approach_speed))
                    currpos.setVSpeed(0)
                    currpos.setProp("_mark", "start_of_star")
                    currpos.setProp("fpidx", k)
                    currpos.setColor("#ff00ff")  # star in MAGENTA
                    revmoves.append(currpos)
                    # logger.debug(":vnav: adding remarkable point: %d %s (%d)" % (k, currpos.getProp("_mark"), len(revmoves)))
                    fcidx = k

        if self.flight.flight_level > 100:
            # descent from FL100 to first approach point
            logger.debug(":vnav: descent to star alt")
            step = actype.descentApproach(10000*FT, alt+STAR_ALT)  # (t, d, altend)
            groundmv = groundmv + step[1]
            currpos, newidx = moveOnCP(fc, fcidx, currpos, step[1])
            currpos.setAltitude(10000*FT)
            currpos.setSpeed(actype.getSI(ACPERF.approach_speed))
            currpos.setVSpeed(actype.getSI(ACPERF.approach_vspeed))
            currpos.setProp("_mark", "descent_fl100_reached")
            fcidx = addCurrentPoint(revmoves, currpos, fcidx, newidx, True)

            if self.flight.flight_level > 240:
                # descent from FL240 to FL100
                logger.debug(":vnav: descent to FL100")
                step = actype.descentToFL100(24000*FT)  # (t, d, altend)
                groundmv = groundmv + step[1]
                currpos, newidx = moveOnCP(fc, fcidx, currpos, step[1])
                currpos.setAltitude(24000*FT)
                currpos.setSpeed(actype.getSI(ACPERF.descentFL100_speed))
                currpos.setVSpeed(actype.getSI(ACPERF.descentFL100_vspeed))
                currpos.setProp("_mark", "descent_fl240_reached")
                fcidx = addCurrentPoint(revmoves, currpos, fcidx, newidx, True)

                if self.flight.flight_level > 240:
                    # descent from cruise above FL240 to FL240
                    logger.debug(":vnav: descent to FL240")
                    step = actype.descentToFL240(self.flight.getCruiseAltitude())  # (t, d, altend)
                    groundmv = groundmv + step[1]
                    currpos, newidx = moveOnCP(fc, fcidx, currpos, step[1])
                    currpos.setAltitude(self.flight.getCruiseAltitude())
                    currpos.setSpeed(actype.getSI(ACPERF.descentFL240_mach))
                    currpos.setVSpeed(actype.getSI(ACPERF.descentFL240_vspeed))
                    currpos.setProp("_mark", "top_of_descent")
                    fcidx = addCurrentPoint(revmoves, currpos, fcidx, newidx, True)
            else:
                # descent from cruise below FL240 to FL100
                logger.debug(":vnav: descent from under FL240 to FL100")
                step = actype.descentToFL100(self.flight.getCruiseAltitude())  # (t, d, altend)
                groundmv = groundmv + step[1]
                currpos, newidx = moveOnCP(fc, fcidx, currpos, step[1])
                currpos.setAltitude(self.flight.getCruiseAltitude())
                currpos.setSpeed(actype.getSI(ACPERF.descentFL100_speed))
                currpos.setVSpeed(actype.getSI(ACPERF.descentFL100_vspeed))
                currpos.setProp("_mark", "top_of_descent")  # !
                fcidx = addCurrentPoint(revmoves, currpos, fcidx, newidx, True)
        else:
            # descent from cruise below FL100 to approach alt
            logger.debug(":vnav: descent from under FL100 to approach alt")
            step = actype.descentApproach(self.flight.getCruiseAltitude(), alt+APPROACH_ALT)  # (t, d, altend)
            groundmv = groundmv + step[1]
            currpos, newidx = moveOnCP(fc, fcidx, currpos, step[1])
            currpos.setAltitude(self.flight.getCruiseAltitude())
            currpos.setSpeed(actype.getSI(ACPERF.approach_speed))
            currpos.setVSpeed(actype.getSI(ACPERF.approach_vspeed))
            currpos.setProp("_mark", "top_of_descent")  # !
            fcidx = addCurrentPoint(revmoves, currpos, fcidx, newidx, True)

        # decelerate to descent speed smoothly
        acceldist = 5000  # we reach cruise speed after 5km horizontal flight
        logger.debug(":vnav: decelerate from cruise speed to first descent speed (which depends on alt...)")
        currpos, newidx = moveOnCP(fc, fcidx, currpos, acceldist)
        groundmv = groundmv + acceldist
        currpos.setAltitude(self.flight.getCruiseAltitude())
        currpos.setSpeed(cruise_speed)  # computed when climbing
        currpos.setVSpeed(0)
        currpos.setProp("_mark", "end_of_cruise_speed")
        fcidx = addCurrentPoint(revmoves, currpos, fcidx, newidx, True)

        top_of_decent_idx = fcidx + 1 # we reach top of descent between idx and idx+1, so we cruise until idx+1
        logger.debug(":vnav: reverse descent at %d after %f" % (top_of_decent_idx, groundmv))
        # we .reverse() array:
        top_of_decent_idx = len(self.flight.flightplan_cp) - top_of_decent_idx  - 1
        logger.debug(":vnav: cruise until %d, descent after %d, remains %f to destination" % (top_of_decent_idx, top_of_decent_idx, groundmv))

        # for f in revmoves:
        #     a = f.altitude()
        #     s = f.speed()
        #     logger.debug(":vnav: revmoves at %s %s: %f %f" % (f.getProp("_mark"), f.getProp("_plan_segment_type"), s if s is not None else -1, a if a is not None else -1))

        # PART 3: Join top of ascent to top of descent at cruise speed
        #
        # We copy waypoints from start of cruise to end of cruise
        logger.debug("CRUISE **********")
        if top_of_decent_idx > top_of_ascent_idx:
            # logger.debug(":vnav: adding cruise: %d -> %d" % (top_of_ascent_idx, top_of_decent_idx))
            for i in range(top_of_ascent_idx, top_of_decent_idx):
                wpt = self.flight.flightplan_cp[i]
                # logger.debug(":vnav: adding cruise: %d %s" % (i, wpt.getProp("_plan_segment_type")))
                p = MovePoint(geometry=wpt["geometry"], properties=wpt["properties"])
                p.setAltitude(self.flight.getCruiseAltitude())
                p.setSpeed(cruise_speed)
                p.setColor("#0000ff")  # Cruise in BLUE
                p.setProp("_mark", "cruise")
                p.setProp("fpidx", i)
                self.moves.append(p)
            logger.debug(":vnav: cruise added (+%d %d)" % (top_of_decent_idx - top_of_ascent_idx, len(self.moves)))
        else:
            logger.warning(":vnav: cruise too short (%d -> %d)" % (top_of_ascent_idx, top_of_decent_idx))

        # PART 4: Add descent and final
        #
        #
        revmoves.reverse()
        self.moves = self.moves + revmoves
        logger.debug(":vnav: descent added (+%d %d)" % (len(revmoves), len(self.moves)))

        return (True, "Movement::vnav completed without restriction")


    def lnav(self):
        """
        Perform lateral navigation for route
        """
        # logger.debug(":lnav: ", len(self.vert_dict.keys()) - startLen, count)
        return (False, "Movement::lnav not implemented")


class ArrivalPath(Movement):

    def __init__(self, flight: Flight, airport: AirportBase):
        Movement.__init__(self, flight=flight, airport=airport)


    def lnav(self):
        # ### LNAV
        # From runway threshold
        # Add touchdown
        # Determine exit runway from aircraft type, weather.
        # Roll to exit
        # Find closest point on taxiway network.
        # Join exit runway to closest point on taxiway network.
        # Find parking's closest point on taxiway network.
        # Route on taxiway from runway exit to parking's closest point on taxiway network.
        # Join parking's closest point on taxiway network to parking.
        # ON BLOCK
        fc = []

        endrolloutpos = MovePoint(geometry=self.end_rollout["geometry"], properties=self.end_rollout["properties"])
        endrolloutpos.setSpeed(TAXI_SPEED)
        endrolloutpos.setColor("#880088")  # parking
        endrolloutpos.setProp("_mark", "end rollout")
        fc.append(endrolloutpos)

        ## TO DO
        # We need to first the first runway exit in front of the aircraft.
        # Move the aircraft to that exit on the runway
        # Then exit to closest point to RWY exit on taxiways
        # Then route on taxiways.

        taxi_start = self.airport.taxiways.nearest_point_on_edge(self.end_rollout)
        print(">>> taxi start", taxi_start)
        if taxi_start[0] is None:
            logger.warning(":lnav: could not find taxi start")
        taxistartpos = MovePoint(geometry=taxi_start[0]["geometry"], properties=taxi_start[0]["properties"])
        taxistartpos.setSpeed(TAXI_SPEED)
        taxistartpos.setColor("#880088")  # parking
        taxistartpos.setProp("_mark", "taxi start")
        fc.append(taxistartpos)

        taxistart_vtx = self.airport.taxiways.nearest_vertex(taxi_start[0])
        print(">>> taxi start vtx", self.end_rollout)
        if taxistart_vtx[0] is None:
            logger.warning(":lnav: could not find taxi end vertex")
        taxistartpos = MovePoint(geometry=taxistart_vtx[0]["geometry"], properties=taxistart_vtx[0]["properties"])
        taxistartpos.setSpeed(TAXI_SPEED)
        taxistartpos.setColor("#880088")  # parking
        taxistartpos.setProp("_mark", "taxi start vertex")
        fc.append(taxistartpos)

        parking = self.airport.parkings[self.flight.ramp]
        print(">> parking", parking)
        # we call the move from packing position to taxiway network the "parking entry"
        parking_entry = self.airport.taxiways.nearest_point_on_edge(parking)
        print(">> parking_entry", parking_entry)

        if parking_entry[0] is None:
            logger.warning(":lnav: could not find parking entry")

        parkingentry_vtx = self.airport.taxiways.nearest_vertex(parking_entry[0])
        if parkingentry_vtx[0] is None:
            logger.warning(":lnav: could not find parking entry vertex")
        print(">> parkingentry_vtx", parkingentry_vtx)

        # taxi_ride = self.airport.taxiways.AStar(taxistart_vtx[0], parkingentry_vtx[0])
        # print(">> taxi_ride", taxi_ride)

        # for v in taxi_ride:
        #     taxipos = MovePoint(geometry=v["geometry"], properties=v["properties"])
        #     taxipos.setSpeed(TAXI_SPEED)
        #     taxipos.setColor("#880000")  # taxi
        #     taxipos.setProp("_mark", "taxi")
        #     fc.append(taxipos)
        # fc[-1].setProp("_mark", "taxi end vertex")

        parkingentrypos = MovePoint(geometry=parking_entry[0]["geometry"], properties=parking_entry[0]["properties"])
        parkingentrypos.setSpeed(SLOW_SPEED)
        parkingentrypos.setColor("#880088")  # parking
        parkingentrypos.setProp("_mark", "taxi end")
        fc.append(parkingentrypos)

        parkingpos = MovePoint(geometry=parking["geometry"], properties=parking["properties"])
        parkingpos.setSpeed(0)
        parkingpos.setColor("#880088")  # parking
        parkingpos.setProp("_mark", "parking")
        fc.append(parkingpos)

        self.taxi = fc

        return (False, "ArrivalPath::lnav completed")


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
        # Initial climb to (opposite) runway threshold
        fc = []

        parking = self.airport.parkings[self.flight.ramp]
        print(">> parking", parking)
        parkingpos = MovePoint(geometry=parking["geometry"], properties=parking["properties"])
        parkingpos.setSpeed(0)
        parkingpos.setColor("#880088")  # parking
        parkingpos.setProp("_mark", "parking")
        fc.append(parkingpos)

        # we call the move from packing position to taxiway network the "pushback"
        pushback_end = self.airport.taxiways.nearest_point_on_edge(parking)
        print(">> pushback_end", pushback_end)
        if pushback_end[0] is None:
            logger.warning(":lnav: could not find pushback end")

        pushbackpos = MovePoint(geometry=pushback_end[0]["geometry"], properties=pushback_end[0]["properties"])
        pushbackpos.setSpeed(SLOW_SPEED)
        pushbackpos.setColor("#880088")  # parking
        pushbackpos.setProp("_mark", "pushback")
        fc.append(pushbackpos)

        pushback_vtx = self.airport.taxiways.nearest_vertex(pushback_end[0])
        print(">> pushback_vtx", pushback_vtx)
        if pushback_vtx[0] is None:
            logger.warning(":lnav: could not find pushback end vertex")


        ## TO DO
        # We need to taxi to the START OF TAKEOFF QUEUE position,
        # then move to (add) each queue position, then add the taxi end
        # which is the closest point to take-off hold.


        taxi_end = self.airport.taxiways.nearest_point_on_edge(self.takeoff_hold)
        print(">> taxi_end", taxi_end)
        if taxi_end[0] is None:
            logger.warning(":lnav: could not find taxi end")

        taxiend_vtx = self.airport.taxiways.nearest_vertex(taxi_end[0])
        print(">> taxiend_vtx", taxiend_vtx)
        if taxiend_vtx[0] is None:
            logger.warning(":lnav: could not find taxi end vertex")

        # taxi_ride = self.airport.taxiways.AStar(pushback_vtx, taxiend_vtx)

        # for v in taxi_ride:
        #     taxipos = MovePoint(geometry=v["geometry"], properties=v["properties"])
        #     taxipos.setSpeed(TAXI_SPEED)
        #     taxipos.setColor("#880000")  # taxi
        #     taxipos.setProp("_mark", "taxi")
        #     fc.append(taxipos)
        # fc[-1].setProp("_mark", "taxi end vertex")

        taxiendpos = MovePoint(geometry=taxi_end[0]["geometry"], properties=taxi_end[0]["properties"])
        taxiendpos.setSpeed(TAXI_SPEED)
        taxiendpos.setColor("#880088")  # parking
        taxiendpos.setProp("_mark", "taxi end")
        fc.append(taxiendpos)

        takeoffholdpos = MovePoint(geometry=self.takeoff_hold["geometry"], properties=self.takeoff_hold["properties"])
        takeoffholdpos.setSpeed(0)
        takeoffholdpos.setColor("#880088")  # parking
        takeoffholdpos.setProp("_mark", "takeoff hold")
        fc.append(takeoffholdpos)

        self.taxi = fc

        return (False, "DeparturePath::lnav completed")
