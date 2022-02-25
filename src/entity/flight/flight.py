import logging
from datetime import datetime, timezone

from ..airspace import FlightPlan
from ..airport import Airport
from ..business import Airline
from ..aircraft import Aircraft
from ..constants import PAYLOAD, FLIGHT_PHASE
from ..utils import FT

logger = logging.getLogger("Flight")


class Flight:

    def __init__(self, operator: Airline, number: str, scheduled: str, departure: Airport, arrival: Airport, aircraft: Aircraft, linked_flight: 'Flight' = None):
        self.number = number
        self.departure = departure
        self.arrival = arrival
        self.linked_flight = linked_flight
        self.managedAirport = None
        self.scheduled = scheduled
        self.estimated = None
        self.actual = None
        self.schedule_history = None  # [(timestamp, {ETA|ETD|STA|STD}, datetime)]
        self.operator = operator
        self.aircraft = aircraft
        self.ramp = None
        self.turnaround = None
        self.codeshare = None
        self.phase = FLIGHT_PHASE.SCHEDULED if scheduled else FLIGHT_PHASE.UNKNOWN
        self.flight_level = 0
        self.runway = None
        self.flightplan = None
        self.flightplan_cp = []
        self.procedure = None   # (RWY, SID), or (STAR, APPCH, RWY)

        self.flight_type = PAYLOAD.PAX
        try:
            if int(number) > 5000:
                if int(number) > 9900:
                    self.flight_type = PAYLOAD.TECH
                else:
                    self.flight_type = PAYLOAD.CARGO
        except ValueError:
            self.flight_type = PAYLOAD.PAX

        if linked_flight is not None and linked_flight.linked_flight is None:
            linked_flight.setLinkedFlight(self)


    def getId(self) -> str:
        s = datetime.fromisoformat(self.scheduled)
        return self.operator.iata + self.number + "-S" + s.astimezone(tz=timezone.utc).strftime("%Y%m%d%H%M")


    def setLinkedFlight(self, linked_flight: 'Flight'):
        self.linked_flight = linked_flight
        logger.debug(":setLinkedFlight: %s linked to %s" % (self.getId(), linked_flight.getId()))


    def setFL(self, flight_level: int):
        self.flight_level = flight_level
        if flight_level <= 100:
            logger.warning(":setFL: %d" % self.flight_level)
        else:
            logger.debug(":setFL: %d" % self.flight_level)


    def setTurnaround(self, turnaround: 'Turnaround'):
        self.turnaround = turnaround


    def getCruiseAltitude(self):
        return self.flight_level * 100 * FT


    def setRamp(self, ramp):
        name = ramp.getProp("name")
        if name in self.managedAirport.ramps.keys():
            self.ramp = ramp
            logger.debug(":setRamp: %s" % name)
        else:
            logger.warning(":setRamp: %s not found" % name)


    def setGate(self, gate):
        self.gate = gate
        logger.debug(":setGate: %s" % self.gate)


    def loadFlightPlan(self):
        self.flightplan = FlightPlan(managedAirport=self.managedAirport.icao, fromICAO=self.departure.icao, toICAO=self.arrival.icao)

        fplen = len(self.flightplan.nodes())
        logger.debug(":loadFlightPlan: loaded %d waypoints" % fplen)

        if fplen < 4:  # 4 features means 3 nodes (dept, fix, arr) and LineString.
            logger.warning(":loadFlightPlan: flight_plan is too short %d" % fplen)


    def trimFlightPlan(self):
        fpcp = self.flightplan.toAirspace(self.managedAirport.airspace)
        if fpcp[1] > 0:
            logger.warning(":trimFlightPlan: unidentified %d waypoints" % fpcp[1])
        logger.debug(":trimFlightPlan: identified %d waypoints, first=%s" % (len(fpcp[0]), fpcp[0][0]))
        return fpcp[0]


    def setEstimatedTime(self, dt: datetime):
        self.estimated = dt
        self.schedule_history.append((datetime.now(), "ET", dt))


    def setActualTime(self, dt: datetime):
        self.actual = dt
        self.schedule_history.append((datetime.now(), "AT", dt))


    def plan(self):
        #
        # LNAV DEPARTURE TO ARRIVAL
        #
        if self.flightplan is None:
            self.loadFlightPlan()
        normplan = self.trimFlightPlan()

        # DEPARTURE AND CRUISE
        depapt = self.departure

        if depapt.has_sids():
            logger.debug(":plan: using procedures for departure airport %s" % depapt.icao)
            # Departure runway
            rwydep = depapt.selectRunway(self)
            if rwydep is not None:
                logger.debug(":plan: %s using runway %s" % (depapt.icao, rwydep.name))
                planpts = rwydep.getRoute()
                planpts[0].setProp("_plan_segment_type", "origin/rwy")
                planpts[0].setProp("_plan_segment_name", depapt.icao+"/"+rwydep.name)
            else:
                logger.warning(":plan: departure airport %s has no runway, leaving from center of airport" % (depapt.icao))
                planpts = depapt
                planpts[0].setProp("_plan_segment_type", "origin")
                planpts[0].setProp("_plan_segment_name", depapt.icao)

            # SID
            sid = depapt.getSID(rwydep)  # !!
            if sid is not None:
                logger.debug(":plan: %s using SID %s" % (depapt.icao, sid.name))
                ret = depapt.procedures.getRoute(sid, self.managedAirport.airspace)
                Flight.setProp(ret, "_plan_segment_type", "sid")
                Flight.setProp(ret, "_plan_segment_name", sid.name)
                planpts = planpts + ret
            else:
                logger.warning(":plan: %s has no SID for %s" % (depapt.icao, rwydep.name))

            # Cruise: We have a SID so we need to remove the first point at least (=departure airport)
            normplan = normplan[1:]
            Flight.setProp(normplan, "_plan_segment_type", "cruise")
            Flight.setProp(normplan, "_plan_segment_name", depapt.icao+"-"+self.arrival.icao)
            planpts = planpts + normplan

        else:
            # Leave departure airport and cruise
            logger.debug(":plan: departure airport %s has no procedure, flying straight" % depapt.icao)
            planpts = normplan
            planpts[0].setProp("_plan_segment_type", "origin")
            planpts[0].setProp("_plan_segment_name", depapt.icao)

        # ARRIVAL
        arrapt = self.arrival

        if arrapt.has_stars():
            if arrapt.has_rwys():
                rwy = arrapt.selectRunway(self)
                self.runway = rwy
                logger.debug(":plan: %s using runway %s" % (arrapt.icao, rwy.name))
                # STAR
                if rwy is not None:
                    star = arrapt.getSTAR(rwy)
                    if star is not None:
                        logger.debug(":plan: %s using STAR %s" % (arrapt.icao, star.name))
                        ret = arrapt.procedures.getRoute(star, arrapt.airspace)
                        Flight.setProp(ret, "_plan_segment_type", "star")
                        Flight.setProp(ret, "_plan_segment_name", star.name)
                        planpts = planpts[:-1] + ret + [planpts[-1]]  # insert STAR before airport
                        # APPCH
                        appch = arrapt.getApproach(star, rwy)
                        if appch is not None:
                            logger.debug(":plan: %s using APPCH %s" % (arrapt.icao, appch.name))
                            ret = arrapt.procedures.getRoute(appch, arrapt.airspace)
                            Flight.setProp(ret, "_plan_segment_type", "appch")
                            Flight.setProp(ret, "_plan_segment_name", appch.name)
                            if len(planpts) > 2 and len(ret) > 0 and planpts[-2].id == ret[0].id:
                                logger.debug(":plan: duplicate end STAR/begin APPCH %s removed" % ret[0].id)
                                planpts = planpts[:-2] + ret + [planpts[-1]]  # remove last point of STAR
                            else:
                                planpts = planpts[:-1] + ret + [planpts[-1]]  # insert APPCH before airport
                        else:
                            logger.warning(":plan: %s no APPCH for %s %s " % (arrapt.icao, star.name, rwy.name))
                    else:
                        logger.warning(":plan: %s no STAR for runway %s" % (arrapt.icao, rwy.name))

                    # RWY
                    ret = rwy.getRoute()
                    Flight.setProp(ret, "_plan_segment_type", "rwy")
                    Flight.setProp(ret, "_plan_segment_name", rwy.name)
                    planpts = planpts[:-1] + ret  # no need to add last point which is arrival airport
                self.procedure = (star, appch, rwy)
            else:  # no runways, can't do much, we are done
                logger.warning(":plan: no runway for %s" % (arrapt.icao))
        else:  # no star, we are done, we arrive in a straight line
            logger.warning(":plan: arrival airport %s has no procedure, flying straight" % (arrapt.icao))

        self.flightplan_cp = planpts
        # printFeatures(self.flightplan_cp, "plan")
        return (True, "Flight::plan: planned")

    @staticmethod
    def setProp(arr: list, propname: str, value: str):
        for a in arr:
            a.setProp(propname, value)


class Arrival(Flight):

    def __init__(self, number: str, scheduled: str, managedAirport: Airport, origin: Airport, operator: Airline, aircraft: Aircraft, linked_flight: 'Flight' = None):
        Flight.__init__(self, number=number, scheduled=scheduled, departure=origin, arrival=managedAirport, operator=operator, aircraft=aircraft, linked_flight=linked_flight)
        self.managedAirport = managedAirport


class Departure(Flight):

    def __init__(self, number: str, scheduled: str, managedAirport: Airport, destination: Airport, operator: Airline, aircraft: Aircraft, linked_flight: 'Flight' = None):
        Flight.__init__(self, number=number, scheduled=scheduled, departure=managedAirport, arrival=destination, operator=operator, aircraft=aircraft, linked_flight=linked_flight)
        self.managedAirport = managedAirport
