#
import logging
import json
import random
import time
from datetime import datetime, timedelta, timezone

import redis
# from pottery import RedisDict

from emitpy.managedairport import ManagedAirport
from emitpy.business import Airline, Company
from emitpy.aircraft import AircraftPerformance, Aircraft
from emitpy.flight import Arrival, Departure, ArrivalMove, DepartureMove
from emitpy.service import Service, ServiceMove, FlightServices, Mission, MissionMove
from emitpy.emit import Emit, ReEmit
from emitpy.broadcast import EnqueueToRedis, Queue
# pylint: disable=W0611
from emitpy.business import AirportManager
from emitpy.constants import SERVICE_PHASE, MISSION_PHASE, FLIGHT_PHASE, FEATPROP, ARRIVAL, LIVETRAFFIC_QUEUE, LIVETRAFFIC_FORMATTER
from emitpy.constants import INTERNAL_QUEUES, ID_SEP, REDIS_TYPE, REDIS_DB, key_path, REDIS_DATABASE, REDIS_PREFIX
from emitpy.constants import MANAGED_AIRPORT_KEY, MANAGED_AIRPORT_LAST_UPDATED, AIRAC_CYCLE
from emitpy.parameters import REDIS_CONNECT, METAR_HISTORICAL, XPLANE_FEED
from emitpy.airport import Airport, AirportBase
from emitpy.airspace import Metar
from emitpy.utils import NAUTICAL_MILE

logger = logging.getLogger("EmitApp")


class StatusInfo:

    def __init__(self, status: int, message: str, data):
        self.status = status
        self.message = message
        self.data = data

    def __str__(self):
        return json.dumps({
            "status": self.status,
            "message": self.message,
            "data": self.data
        })


SAVE_TO_FILE = False  # for debugging purpose
SAVE_TRAFFIC = True


def BOOTSTRAP_REDIS():
    not_connected = True
    attempts = 0
    while not_connected and attempts < 10:
        r = redis.Redis(**REDIS_CONNECT)
        try:
            pong = r.ping()
            not_connected = False
            logger.info("BOOTSTRAP_REDIS: connected")
        except redis.RedisError:
            logger.warning("BOOTSTRAP_REDIS: cannot connect, retrying...")
            attempts = attempts + 1
            time.sleep(2)

    if not_connected:
        logger.error("BOOTSTRAP_REDIS: cannot connect")
        return False

    prevdb = r.client_info()["db"]
    r.select(REDIS_DB.REF.value)
    k = key_path(REDIS_PREFIX.AIRPORT.value, MANAGED_AIRPORT_KEY)
    a = r.json().get(k)
    r.select(prevdb)
    return a is not None and MANAGED_AIRPORT_LAST_UPDATED in a and AIRAC_CYCLE in a


class RouteApp(ManagedAirport):

    def __init__(self, airport):

        ManagedAirport.__init__(self, airport=airport, app=self)

        self.local_timezone = datetime.now(timezone.utc).astimezone().tzinfo

        self.redis_pool = None
        self.redis = None
        self.gas = None

        self._use_redis = BOOTSTRAP_REDIS()

        # If Redis is defined before calling init(), it will use it.
        # Otherwise, it will use the data files.
        if not self._use_redis:  # If caching data we MUST preload them from files
            logger.info(f":init: not using Redis for data")
            ret = self.init()    # call init() here to use data from data files
            if not ret[0]:
                logger.warning(ret[1])

        # (Mandatory) use of Redis starts here
        # Redis is sometimes slow to start, wait for it
        not_connected = True
        attempts = 0

        while not_connected and attempts < 10:
            self.redis_pool = redis.ConnectionPool(**REDIS_CONNECT)
            self.redis = redis.Redis(connection_pool=self.redis_pool)

            try:
                pong = self.redis.ping()
                not_connected = False
                logger.info(":init: connected to Redis")
                self.redis.config_set('notify-keyspace-events', "KA")
                logger.debug(f":init: {self.redis.config_get('notify-keyspace-events')}")
                logger.info(":init: keyspace notification enabled")
            except redis.RedisError:
                logger.error(":init: cannot connect to redis, retrying...")
                attempts = attempts + 1
                time.sleep(2)

        if not_connected:
            logger.error(":init: cannot connect to redis")
            return


        if self._use_redis:
            ret = self.check_data()
            if not ret[0]:
                logger.error(ret[1])
                return
            # Init "Global Airport Status" structure.
            # For later use. Used for testing only.
            # self.redis.select(REDIS_DB.CACHE.value)
            # self.gas = RedisDict(None, redis=redis.Redis(connection_pool=self.redis_pool), key='airport')
            # self.gas["managed-airport"] = airport
            # self.redis.select(REDIS_DB.APP.value)
            logger.info(f":init: using Redis for data, {ret[1]}")

        # Default queue(s)
        self.redis.select(REDIS_DB.APP.value)
        self.queues = Queue.loadAllQueuesFromDB(self.redis)
        # logger.debug(":init: checking for default queues..")
        for k, v in INTERNAL_QUEUES.items():
            if k not in self.queues.keys():
                logger.debug(f":init: creating missing default queue {k}..")
                self.queues[k] = Queue(name=k, formatter_name=v, redis=self.redis)
                self.queues[k].save()

        if XPLANE_FEED:  # obstinately harcoded
            k = LIVETRAFFIC_QUEUE
            v = LIVETRAFFIC_FORMATTER
            if k not in self.queues.keys():
                logger.debug(f":init: creating LiveTraffic queue with {LIVETRAFFIC_FORMATTER} formatter")
                self.queues[k] = Queue(name=k, formatter_name=v, redis=self.redis)
                self.queues[k].save()

        ret = self.init(load_airways=True)  # call init() here to use data from Redis
        if not ret[0]:
            logger.warning(ret[1])
            return

        self.loadFromCache()

        logger.debug(":init: initialized. listening.."+ "\n\n")
        # logger.warning("=" * 90)


    def use_redis(self):
        """
        Function that check whether we are using Redis for data.
        If true, we return a redis connection instance ready to be used.
        If false, we return None and the function that called us can choose another path.
        """
        if self._use_redis:
            return redis.Redis(connection_pool=self.redis_pool)
        return None


    def check_data(self):
        prevdb = self.redis.client_info()["db"]
        self.redis.select(REDIS_DB.REF.value)
        k = key_path(REDIS_PREFIX.AIRPORT.value, MANAGED_AIRPORT_KEY)
        a = self.redis.json().get(k)
        self.redis.select(prevdb)
        if a is not None and MANAGED_AIRPORT_LAST_UPDATED in a and AIRAC_CYCLE in a:
            return (True, f"last loaded on {a[MANAGED_AIRPORT_LAST_UPDATED]}, nav data airac cycle {a[AIRAC_CYCLE]}")
        return (False, f"EmitApp::check_data: key '{k}' not found, data not available in Redis")


    def getId(self):
        return emitpy.__NAME__ + ID_SEP + emitpy.__version__


    def getInfo(self):
        return {
            "name": emitpy.__NAME__,
            "description": emitpy.__DESCRIPTION__,
            "copyright": emitpy.__COPYRIGHT__,
            "version": emitpy.__version__,
            "version-name": emitpy.__version_name__
        }

    def getRedis(self, from_pool: bool = False):
        if from_pool:
            return redis.Redis(connection_pool=self.redis_pool)
        return self.redis


    def saveToCache(self):
        logger.debug(":saveToCache: saving .. (this may take a few microseconds)")
        self.airport.manager.saveAllocators(self.redis)
        logger.debug(":saveToCache: ..done")


    def loadFromCache(self):
        logger.debug(":loadFromCache: loading .. (this may take a few microseconds)")
        self.airport.manager.loadAllocators(self.redis)
        logger.debug(":loadFromCache: ..done")


    def shutdown(self):
        logger.debug(":shutdown: ..shutting down..")
        self.saveToCache()
        logger.debug(":shutdown: ..done")


    def find_route(self, airline, flightnumber, scheduled, apt, movetype, actype, ramp, icao24, acreg, runway):
        fromto = "from" if movetype == ARRIVAL else "to"
        logger.info("*" * 110)
        logger.info(f"***** {airline}{flightnumber} {scheduled} {movetype} {fromto} {apt} {actype} {icao24} {acreg} {ramp} {runway}")
        logger.debug("*" * 109)

        logger.debug(":do_flight: airline, airport..")
        # Add pure commercial stuff
        airline = Airline.find(airline, self.redis)
        remote_apt = Airport.find(apt, self.redis)
        aptrange = self.airport.miles(remote_apt)
        logger.debug(":do_flight: ..done")

        logger.debug(":do_flight: remote airport..")
        remote_apt = AirportBase(icao=remote_apt.icao,
                                 iata=remote_apt.iata,
                                 name=remote_apt["properties"]["name"],
                                 city=remote_apt["properties"]["city"],
                                 country=remote_apt["properties"]["country"],
                                 region=remote_apt.region,
                                 lat=remote_apt["geometry"]["coordinates"][1],
                                 lon=remote_apt["geometry"]["coordinates"][0],
                                 alt=remote_apt["geometry"]["coordinates"][2] if len(remote_apt["geometry"]["coordinates"]) > 2 else None)
        ret = remote_apt.load()
        if not ret[0]:
            logger.warning(f":do_flight: remote airport not loaded: {ret}")
            return ret

        prevdb = self.redis.client_info()["db"]
        self._app.redis.select(1)
        remote_apt.save("airports", self.use_redis())
        self._app.redis.select(prevdb)
        logger.debug(f":do_flight: remote airport saved")

        scheduled_dt = datetime.fromisoformat(scheduled)
        if scheduled_dt.tzname() is None:  # has no time zone, uses local one
            scheduled_dt = scheduled_dt.replace(tzinfo=self.timezone)
            logger.debug(":do_flight: scheduled time has no time zone, added managed airport local time zone")

        logger.debug(":do_flight: ..collecting metar for remote airport..")
        dt2 = datetime.now().astimezone(self.timezone) - timedelta(days=1)
        if METAR_HISTORICAL and scheduled_dt < dt2:  # issues with web site to fetch historical metar.
            logger.debug(f":do_flight: ..historical.. ({scheduled})")
            remote_metar = Metar.new(icao=remote_apt.icao, redis=self.redis, method="MetarHistorical")
            remote_metar.setDatetime(moment=scheduled_dt)
            if not remote_metar.hasMetar():  # couldn't fetch historical, use current
                remote_metar = Metar.new(icao=remote_apt.icao, redis=self.redis)
        else:
            remote_metar = Metar.new(icao=remote_apt.icao, redis=self.redis)
        remote_apt.setMETAR(metar=remote_metar)  # calls prepareRunways()
        logger.debug(":do_flight: ..done")

        logger.debug(":do_flight: loading aircraft..")
        acarr = (actype, actype) if type(actype) == str else actype
        actype, acsubtype = acarr
        ac = AircraftPerformance.findAircraftByType(actype, acsubtype, self.use_redis())
        if ac is None:
            return StatusInfo(100, f"aircraft performance not found for {actype} or {acsubtype}", None)
        acperf = AircraftPerformance.find(icao=ac, redis=self.use_redis())
        if acperf is None:
            return StatusInfo(101, f"aircraft performance not found for {ac}", None)
        acperf.load()
        reqfl = acperf.FLFor(aptrange)
        aircraft = Aircraft(registration=acreg, icao24= icao24, actype=acperf, operator=airline)
        aircraft.save(self.redis)
        logger.debug(":do_flight: ..done")

        # logger.info("*" * 90)
        logger.info("***** (%s, %dnm) %s-%s AC %s at FL%d" % (
                    remote_apt.getProp(FEATPROP.CITY.value), aptrange/NAUTICAL_MILE, remote_apt.iata, self._this_airport["IATA"],
                    acperf.typeId, reqfl))
        # logger.debug("*" * 89)

        logger.debug(":do_flight: creating flight..")
        flight = None
        if movetype == ARRIVAL:
            flight = Arrival(operator=airline,
                             number=flightnumber,
                             scheduled=scheduled_dt,
                             managedAirport=self,
                             origin=remote_apt,
                             aircraft=aircraft)
        else:
            flight = Departure(operator=airline,
                               number=flightnumber,
                               scheduled=scheduled_dt,
                               managedAirport=self,
                               destination=remote_apt,
                               aircraft=aircraft)
        flight.setFL(reqfl)
        rampval = self.airport.getRamp(ramp, redis=self.use_redis())
        if rampval is None:
            logger.warning(f":do_flight: ramp {ramp} not found, quitting")
            return StatusInfo(102, f"ramp {ramp} not found", None)

        flight.setRamp(rampval)
        gate = "C99"
        ramp_name = rampval.getName()
        if ramp_name[0] in "A,B,C,D,E".split(",") and len(ramp) < 5:  # does now work for "Cargo Ramp F5" ;-)
            gate = ramp_name
        flight.setGate(gate)

        aircraft.setCallsign(airline.icao+flightnumber)

        logger.debug(":do_flight: ..planning..")
        ret = flight.plan()
        if not ret[0]:
            return StatusInfo(110, f"problem during flight planning", ret[1])

        logger.debug(f":do_flight: route: {flight.printFlightRoute()}")
        logger.debug(f":do_flight: plan : {flight.printFlightPlan()}")

        logger.debug(":do_flight: ..flying..")
        move = None
        if movetype == ARRIVAL:
            move = ArrivalMove(flight, self.airport)
        else:
            move = DepartureMove(flight, self.airport)
        ret = move.move()
        if not ret[0]:
            return StatusInfo(103, f"problem during move", ret[1])
        # move.save()

        return StatusInfo(0, "completed successfully", flight.getId())
