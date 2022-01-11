import random
from datetime import datetime, timedelta
import logging

logger = logging.getLogger("Flightboard")

from .flight import Flight
from .turnaround import Turnaround
from .clearance import Availability

from .constants import PASSENGER, CARGO, DEPARTURE, ARRIVAL

from .airport.home import ManagedAirport


class Flightboard:

    def __init__(self, airport: ManagedAirport, options: object):
        self.manageairport = airport
        self.options = options
        self.movements = {}


    def generate(self):
        """
        Generates a random flightboard
        """
        simstart = datetime.fromisoformat(self.options.get("starttime"))

        simend = simstart + timedelta(days=28)
        maxflights = 999999
        flightcount = 0

        endtime = self.options.get("endtime")
        if endtime is not None:
            simend = datetime.fromisoformat(endtime)
            logger.debug("start time: %s, end time: %s", self.options.get("starttime"), simend)
        else:
            maxflights = self.options.get("flightcount")
            logger.debug("start time: %s, count: %d", self.options.get("starttime"), maxflights)

        # THIS PORTION SCHEDULE FLIGHT. Flights not necessarily be played according to this schedule
        # since we will introduce random delays at all stage of operations.
        # Hour per hour (since max number of movements is given per hour), we schedule all arrivals.
        # We only take "half" the slots for arrival, leaving half of them for departure.
        # Arrivals take random slots from all slots. (they are all available since no departure is scheduled when we do this.)
        # When all arrivals are scheduled, each departure will take the first available slot after its minimal turnaround time completes.
        # When numerous arrival are scheduled in an hour, room will be made for departure after that hour.
        # So less arrival will occur (since slots are taken for departure.)
        # (@todo: split #movements for #departures and #arrivals.)
        #
        simhour = simstart.replace(minute=0, second=0, microsecond=0)
        slotspax = []
        slotscargo = []

        while simhour < simend and flightcount < maxflights:
            current_hour = simhour.timetuple().tm_hour
            numpax = int(self.options.get(["movements", PASSENGER, str(current_hour)]) / 2)
            numcargo = int(self.options.get(["movements", CARGO, str(current_hour)]) / 2)
            nummoves = numpax + numcargo

            if nummoves > (maxflights - flightcount):  # flights left to generate is less than all flights this hour
                paxratio = numpax / nummoves
                nummoves = maxflights - flightcount
                numpax = round(nummoves * paxratio)
                numcargo = nummoves - numpax

            if numpax > 0:
                slotspax_avail = self.manageairport.clearance.available_slots(simhour, ARRIVAL, PASSENGER)
                if numpax <= len(slotspax_avail):
                    slotspax_this_hour = random.sample(slotspax_avail, numpax)
                    slotspax += slotspax_this_hour
                    # reserve them o they are no longer available for cargo
                    for slot in slotspax_this_hour:
                        slot.reservation = self.manageairport.clearance.book(slot)
                        slot.reservation.set_info("payload", PASSENGER)
                        slot.reservation.set_info("move", ARRIVAL)
                        flightcount += 1
                else:
                    logger.warning("mkFlights: PAX: Request %d flights: only %d available", numpax, len(slotspax_avail))
                    numpax = len(slotspax_avail)
                    slotspax_this_hour = slotspax_avail

            if numcargo > 0:
                slotscargo_avail = self.manageairport.clearance.available_slots(simhour, ARRIVAL, CARGO)
                if numcargo <= len(slotscargo_avail):
                    slotscargo_this_hour = random.sample(slotscargo_avail, numcargo)
                    slotscargo += slotscargo_this_hour
                    for slot in slotscargo_this_hour:
                        slot.reservation = self.manageairport.clearance.book(slot)
                        slot.reservation.set_info("payload", CARGO)
                        slot.reservation.set_info("move", ARRIVAL)
                        flightcount += 1
                else:
                    logger.warning("mkFlights: CARGO: Request %d flights: only %d available", numcargo, len(slotscargo_avail))
                    numcargo = len(slotscargo_avail)
                    slotscargo_this_hour = slotscargo_avail

            simhour += timedelta(seconds=3600)

        logger.debug("slots for pax: %s, cargo: %s", len(slotspax), len(slotscargo))

        # schedule actual flight
        for slot in slotspax:
            self.mkFlights(PASSENGER, slot)
        for slot in slotscargo:
            self.mkFlights(CARGO, slot)

        return "Flightboard::generate"


    def mkFlights(self, payload: str, slot: Availability):
        moment = self.manageairport.clearance.time(slot)
        # logger.debug("mkFlights: creating %s: %s...", payload, moment)

        # Select airport "FROM", get distance
        logger.debug("mkFlights: %s", self.manageairport.routes[payload].values())
        afrom = random.choice(list(self.manageairport.routes[payload].values()))
        airln = random.choice(list(self.manageairport.airlines.values()))
        adist = self.manageairport.distance_to(afrom)

        aplty = airln.plane_type_for(payload, adist)
        plane = airln.plane(aplty)

        parking = self.manageairport.findParking(payload, aplty)
        aname = airln.randomFlightname()

        landing_time = moment
        taxi_in_time = self.manageairport.taxi_time(ARRIVAL, payload, parking, landing_time, aplty)
        arrival_time = landing_time + taxi_in_time

        arrival = Flight(name=aname, scheduled=arrival_time, departure=afrom, arrival=self.manageairport, operator=airln, aircraft=plane, gate=parking)

        self.movements[aname] = arrival

        dto = False
        while not dto:
            ato = random.choice(list(self.manageairport.routes[payload].values()))
            ddist = self.manageairport.distance_to(ato)
            if ddist < plane.aircraft_type.range():
                dto = ato

        rotation_duration = Turnaround.template(airln, aplty)

        dname = airln.randomFlightname()
        departure_time = arrival_time + rotation_duration
        taxi_out_time = self.manageairport.taxi_time(DEPARTURE, payload, parking, departure_time, aplty)

        tentative_takeoff_time = departure_time + taxi_out_time
        # We need to find a slot:
        # reservation = self.manageairport.clearance.reserve_next_slot(DEPARTURE, tentative_takeoff_time)
        takeoff_time = tentative_takeoff_time  # reservation.moment

        ddiff = tentative_takeoff_time - takeoff_time
        if ddiff.seconds > (10 * 60):
            # we adjust the announced takeoff time:
            departure_time = takeoff_time - taxi_out_time

        departure = Flight(name=dname, scheduled=departure_time, departure=self.manageairport, arrival=dto, operator=airln, aircraft=plane, gate=parking)
        self.movements[dname] = departure


"""
Algorithm


1. Load environment

1.1 Load simulation Parameters

        Slot time. If none, no slotted time, time is totally arbitrary.
        Flight density is number of mouvement per hour.
        Maximum capacity per runway is #slot/hour / 2 (departure or arrival) if no contengency.

        We can imagine a "density per hour": [2, 4, 8, 22, 17... ] 24 values for each hour of the day.
        We can even imagine a density type: PAX or CARGO per hour: [[2, 8], [0, 6], [20, 2]...]

    (check consistency of parameters, for ex. 24 density per day, etc.)

1.2 Load airports

1.2.1 Load ManagedAirport
  - Separate runways for departure and arrival?
  - Runway time slotted? If yes, make slots.

1.2.2 Load other airports
  - Load from global airport database.
  - If other airport has detail, create details, otherwise create normal.


2. Build a set of arrival and departure times.

  2.1 To do later: Allow for planes on the ground (already arrived). Schedule them for departure only.
                   First departure is at or after start time of simulation.
                   Determine all times of departure (occupied slots).
                   SCHEDULED time is 30 minutes (parameter) before time of slot, rounded (FLOOR!) to 5~10 minutes for display.
                   I.e. slot = 15:23, SCHEDULED(displayed)= 14:53 rounded to 14:50.

  2.2. First arrival is at or after start time of simulation (i.e. plane may fly in __before__ the start time of the simulation.)


    For each hour in simulation:

        Get total number of movements (PAX+CARGO).
        There will be half that many Arrivals.
        Randomly pickup number of arrivals slots with Departure.
        Split spots between PAX and CARGO.
        We now have a set of times of arrival and whether it is a PAX or CARGO arriving.

        Ignore those before start of simulation.

        Schedule a random flight arrival.
        Schedule its planned rotation.
        Schedule and make departure flight.



        Depending on density, pickup arrival slots in current hour.
        I.e. if density = 20 mvts per hour, schedule 10 arrivals.
        (At beginning of simulation, there will be less movement, since no departure.
        At end of simulation too, since only departure, no more arrival.)


        For this hour: Loop either for number of flights or "until" end datetime is reached:

            Determine if PAX or CARGO (How? from density?)
            Pickup slot/time for arrival. Round time to 5 minutes (parameter).
            Is at least one slot or "time interval"(parameter) after previous one.
            Depends on "density" of flight. Density of flights expressed in % of max capacity. Max capacity = #runways * 6

            Pickup airport source at some distance for arrival.
            Pickup airline (from managed airport or remote airport if available).
            Pickup plane for distance.
            Pickup parking suitable for plane, may be dependant on PAX/CARGO and airline (favorite apron/gates)

            Pickup airport destination at about same distance for departure.
            Set "global" rotation duration, function of aircraft size.
            Set departure time at least (total_rotation_duration * (coefficient(parameter) > 1.0)) after arrival. Add random time (parameter).
            Pickup next avaialble departure slot/time.



3. (Optional) From set of arrival/departure, build rotations

  Schedule rotation services.
  Attempt to use queue for service vehicle.


At the end of this first phase, we have a formal schedule for arrivals, departures,
and service of planes during rotation.


"""
