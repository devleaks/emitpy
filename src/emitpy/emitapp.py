import logging
import json
import random
import redis
import time

from redis.commands.json.path import Path

# from pottery import RedisDict

from datetime import datetime, timedelta, timezone

from emitpy.managedairport import ManagedAirport
from emitpy.business import Airline, Company
from emitpy.aircraft import AircraftType, AircraftPerformance, Aircraft
from emitpy.flight import Arrival, Departure, ArrivalMove, DepartureMove
from emitpy.service import Service, ServiceMove, FlightServices, Mission, MissionMove
from emitpy.emit import Emit, ReEmit, EnqueueToRedis, Queue
from emitpy.business import AirportManager
from emitpy.constants import SERVICE, SERVICE_PHASE, MISSION_PHASE, FLIGHT_PHASE, FEATPROP, ARRIVAL, DEPARTURE, LIVETRAFFIC_QUEUE
from emitpy.constants import INTERNAL_QUEUES, ID_SEP, REDIS_TYPE, REDIS_DB, key_path, REDIS_DATABASE, REDIS_PREFIX
from emitpy.constants import MANAGED_AIRPORT_KEY, MANAGED_AIRPORT_LAST_UPDATED
from emitpy.parameters import DATA_IN_REDIS, REDIS_CONNECT, METAR_HISTORICAL, XPLANE_FEED
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


class EmitApp(ManagedAirport):

    def __init__(self, airport):

        ManagedAirport.__init__(self, airport=airport, app=self)

        self.local_timezone = datetime.now(timezone.utc).astimezone().tzinfo
        self._use_redis = False

        self.redis_pool = None
        self.redis = None
        self.gas = None

        # If Redis is defined before calling init(), it will use it.
        # Otherwise, it will use the data files.
        if not DATA_IN_REDIS:  # If caching data we MUST preload them from files
            ret = self.init()  # call init() here to use data from data files
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
                self.redis.config_set('notify-keyspace-events', "Kgz")  #KA
                logger.debug(f":init: {self.redis.config_get('notify-keyspace-events')}")
                logger.info(":init: keyspace notification enabled")
            except redis.RedisError:
                logger.error(":init: cannot connect to redis, retrying...")
                attempts = attempts + 1
                time.sleep(2)

        if not_connected:
            logger.error(":init: cannot connect to redis")
            return


        if DATA_IN_REDIS:
            ret = self.check_data()
            if not ret[0]:
                logger.error(ret[1])
                return
            # Init "Global Airport Status" structure.
            # For later use. Used for testing only.
            # self.redis.select(REDIS_DB.CACHE.value)
            # self.gas = RedisDict(None, redis=redis.Redis(connection_pool=self.redis_pool), key='airport')
            # self.gas["managed-airport"] = airport
            # print(self.gas)
            # self.redis.select(REDIS_DB.APP.value)
        logger.debug(f":init: data last loaded on {ret[1]}")


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
            v = LIVETRAFFIC_QUEUE
            if k not in self.queues.keys():
                logger.debug(f":init: creating LiveTraffic queue..")
                self.queues[k] = Queue(name=k, formatter_name=v, redis=self.redis)
                self.queues[k].save()

        ret = self.init()  # call init() here to use data from Redis
        if not ret[0]:
            logger.warning(ret[1])
            return

        logger.debug(":init: initialized. listening..")
        logger.debug("=" * 90)


    def use_redis(self):
        """
        Function that check whether we are using Redis for data.
        If true, we return a redis connection instance ready to be used.
        If false, we return None and the function that called us can choose another path.
        """
        if DATA_IN_REDIS:
            return redis.Redis(connection_pool=self.redis_pool)
        return None


    def check_data(self):
        prevdb = self.redis.client_info()["db"]
        self.redis.select(REDIS_DB.REF.value)
        k = key_path(REDIS_PREFIX.AIRPORT.value, MANAGED_AIRPORT_KEY)
        a = self.redis.json().get(k)
        self.redis.select(prevdb)
        if a is not None and MANAGED_AIRPORT_LAST_UPDATED in a:
            return (True, a[MANAGED_AIRPORT_LAST_UPDATED])
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
        logger.debug(":saveToCache: .. done")


    def loadFromCache(self):
        logger.debug(":loadFromCache: loading .. (this may take a few microseconds)")
        self.airport.manager.loadAllocators(self.redis)
        logger.debug(":loadFromCache: .. done")


    def do_flight(self, queue, emit_rate, airline, flightnumber, scheduled, apt, movetype, acarr, ramp, icao24, acreg, runway, do_services: bool = False, actual_datetime: str = None):
        logger.debug(":do_flight: Airline, airport ..")
        # Add pure commercial stuff
        airline = Airline.find(airline, self.redis)
        remote_apt = Airport.find(apt, self.redis)
        aptrange = self.airport.miles(remote_apt)
        logger.debug(":do_flight: .. done")

        logger.debug(":do_flight: loading other airport..")
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
            logger.warning(f":do_flight: other airport not loaded: {ret}")
            return ret

        prevdb = self.redis.client_info()["db"]
        self._app.redis.select(1)
        remote_apt.save("airports", self._app.redis)
        self._app.redis.select(prevdb)
        logger.debug(f":do_flight: other airport saved")

        scheduled_dt = datetime.fromisoformat(scheduled)
        if scheduled_dt.tzname() is None:  # has no time zone, uses local one
            scheduled_dt = scheduled_dt.replace(tzinfo=self.timezone)
            logger.debug(":do_flight: scheduled time has no time zone, added managed airport local time zone")

        logger.debug(":do_flight: .. collecting metar ..")
        dt2 = datetime.now().astimezone(self.timezone) - timedelta(days=1)
        if METAR_HISTORICAL and scheduled_dt < dt2:  # issues with web site to fetch historical metar.
            logger.debug(f":do_flight: ..historical.. ({scheduled})")
            remote_metar = Metar.new(icao="OTHH", redis=self.redis, method="MetarHistorical")
            remote_metar.setDatetime(moment=scheduled_dt)
            if not remote_metar.hasMetar():  # couldn't fetch histoorical, use current
                remote_metar = Metar.new(icao=remote_apt.icao, redis=self.redis)
        else:
            remote_metar = Metar.new(icao=remote_apt.icao, redis=self.redis)
        remote_apt.setMETAR(metar=remote_metar)  # calls prepareRunways()
        logger.debug(":do_flight: ..done")

        logger.debug(":do_flight: loading aircraft ..")
        actype, acsubtype = acarr
        ac = AircraftPerformance.findAircraftByType(actype, acsubtype, self.redis)
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

        logger.info("*" * 90)
        logger.info("*** (%s, %dnm) %s-%s AC %s at FL%d" % (
                    remote_apt.getProp(FEATPROP.CITY.value), aptrange/NAUTICAL_MILE, remote_apt.iata, self._this_airport["IATA"],
                    acperf.typeId, reqfl))
        logger.debug("*" * 90)

        logger.debug(":do_flight: creating flight ..")
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

        logger.debug(":do_flight: .. planning ..")
        flight.plan()

        logger.debug(":do_flight: .. flying ..")
        move = None
        if movetype == ARRIVAL:
            move = ArrivalMove(flight, self.airport)
            sync = FLIGHT_PHASE.TOUCH_DOWN.value
            svc_sync = FLIGHT_PHASE.ONBLOCK.value
        else:
            move = DepartureMove(flight, self.airport)
            sync = FLIGHT_PHASE.TAKE_OFF.value
            svc_sync = FLIGHT_PHASE.OFFBLOCK.value
        ret = move.move()
        if not ret[0]:
            return StatusInfo(103, f"problem during move", ret[1])
        # move.save()

        logger.debug(":do_flight: ..emission positions..")
        emit = Emit(move)
        ret = emit.emit(emit_rate)
        if not ret[0]:
            return StatusInfo(104, f"problem during emit", ret[1])
        # emit.save()

        logger.debug(":do_flight: .. scheduling ..")
        # Schedule actual time if supplied
        logger.debug(f":do_flight: scheduled={scheduled}, actual={actual_datetime}")
        emit_time_str = actual_datetime if actual_datetime is not None else scheduled
        emit_time = datetime.fromisoformat(emit_time_str)
        if emit_time.tzname() is None:  # has no time zone, uses local one
            emit_time = emit_time.replace(tzinfo=self.timezone)
            logger.debug(":do_flight: scheduled time has no time zone, added managed airport local time zone")

        logger.debug(emit.getMarkList())
        ret = emit.schedule(sync, emit_time)
        if not ret[0]:
            return StatusInfo(105, f"problem during schedule", ret[1])

        logger.debug(":do_flight: .. saving ..")
        if SAVE_TO_FILE:
            ret = emit.saveFile()
            if not ret[0]:
                return StatusInfo(106, f"problem during schedule", ret[1])
        ret = emit.save(redis=self.redis)
        if not ret[0]:
            return StatusInfo(110, f"problem during schedule", ret[1])

        logger.debug(":do_flight: .. broadcasting positions ..")
        formatted = EnqueueToRedis(emit=emit, queue=self.queues[queue], redis=self.redis)
        ret = formatted.format()
        if not ret[0]:
            return StatusInfo(107, f"problem during formatting", ret[1])
        ret = formatted.save()
        if not ret[0] and ret[1] != "EnqueueToRedis::save key already exist":
            return StatusInfo(108, f"problem during formatted output save", ret[1])
        ret = formatted.enqueue()
        if not ret[0]:
            return StatusInfo(109, f"problem during enqueue", ret[1])

        self.airport.manager.saveAllocators(self.redis)

        if not do_services:
            logger.info(":do_flight: SAVED " + ("*" * 84))
            logger.debug(":do_flight: .. done")
            return StatusInfo(0, "completed successfully", flight.getId())

        logger.debug(":do_flight: .. servicing ..")
        st = emit.getRelativeEmissionTime(sync)
        bt = emit.getRelativeEmissionTime(svc_sync)  # 0 for departure...
        td = bt - st
        blocktime = emit_time + timedelta(seconds=td)

        # @todo: pass service operator
        operator = Company(orgId="Airport Operator", classId="Airport Operator", typeId="Airport Operator", name="MATAR")
        # operator = self.airport.manager.getCompany(operator)

        flight_service = FlightServices(flight, operator)
        flight_service.setManagedAirport(self.airport)
        ret = flight_service.service()
        if not ret[0]:
            return StatusInfo(150, f"problem during flight service", ret[1])

        logger.debug(":do_flight: .. moving service vehicle ..")
        ret = flight_service.move()
        if not ret[0]:
            return StatusInfo(151, f"problem during flight service movement creation", ret[1])

        logger.debug(":do_flight: .. emission positions service vehicle ..")
        ret = flight_service.emit(emit_rate)
        if not ret[0]:
            return StatusInfo(152, f"problem during flight service emission", ret[1])

        logger.debug(":do_flight: .. scheduling service vehicle ..")
        ret = flight_service.schedule(blocktime)
        if not ret[0]:
            return StatusInfo(153, f"problem during flight service scheduling", ret[1])

        logger.debug(":do_flight: .. saving service vehicle ..")
        if SAVE_TO_FILE:
            ret = flight_service.saveFile()
            if not ret[0]:
                return StatusInfo(154, f"problem during flight service scheduling", ret[1])
        ret = flight_service.save(redis=self.redis)
        if not ret[0]:
            return StatusInfo(155, f"problem during flight service save in Redis", ret[1])

        logger.debug(":do_flight: .. broadcasting positions ..")
        ret = flight_service.enqueuetoredis(self.queues[queue])
        if not ret[0]:
            return StatusInfo(156, f"problem during enqueue of services", ret[1])

        self.airport.manager.saveAllocators(self.redis)

        logger.debug(":do_flight: ..done, service included.")
        return StatusInfo(0, "completed successfully", flight.getId())


    def do_service(self, queue, emit_rate, operator, service, quantity, ramp, aircraft, vehicle_ident, vehicle_icao24, vehicle_model, vehicle_startpos, vehicle_endpos, scheduled):
        logger.debug(":do_service: loading aircraft ..")
        acperf = AircraftPerformance.find(aircraft, redis=self.use_redis())
        if acperf is None:
            return StatusInfo(200, f"EmitApp:do_service: aircraft performance {aircraft} not found", None)
        acperf.load()
        logger.debug(f":do_flight: .. done {acperf.available}")

        operator = Company(orgId="Airport Operator", classId="Airport Operator", typeId="Airport Operator", name="MATAR")

        logger.debug(":do_service: creating service ..")
        rampval = self.airport.getRamp(ramp, redis=self.use_redis())
        if rampval is None:
            return StatusInfo(201, f"EmitApp:do_service: ramp {ramp} not found", None)
        scheduled_dt = datetime.fromisoformat(scheduled)
        if scheduled_dt.tzname() is None:  # has no time zone, uses local one
            scheduled_dt = scheduled_dt.replace(tzinfo=self.timezone)
            logger.debug(":do_service: scheduled time has no time zone, added managed airport local time zone")
        this_service = Service.getService(service)(scheduled=scheduled_dt,
                                                   ramp=rampval,
                                                   operator=operator,
                                                   quantity=quantity)
        this_service.setAircraftType(acperf)
        this_vehicle = self.airport.manager.selectServiceVehicle(operator=operator, service=this_service, reqtime=scheduled_dt, model=vehicle_model, registration=vehicle_ident, use=True)
        if this_vehicle is None:
            return StatusInfo(202, f"EmitApp:do_service: vehicle not found", None)
        this_vehicle.setICAO24(vehicle_icao24)
        startpos = self.airport.selectServicePOI(vehicle_startpos, service, redis=self.use_redis())
        if startpos is None:
            return StatusInfo(203, f"EmitApp:do_service: start position {vehicle_startpos} for {service} not found", None)
        this_vehicle.setPosition(startpos)  # this is the start position for the vehicle
        nextpos = self.airport.selectServicePOI(vehicle_endpos, service, redis=self.use_redis())
        if nextpos is None:
            return StatusInfo(204, f"EmitApp:do_service: start position {vehicle_endpos} for {service} not found", None)
        this_vehicle.setNextPosition(nextpos)  # this is the position the vehicle is going to after service

        logger.debug(":do_service: .. moving ..")
        move = ServiceMove(this_service, self.airport)
        ret = move.move()
        if not ret[0]:
            return StatusInfo(205, f"problem during service move", ret[1])
        if SAVE_TO_FILE:
            ret = move.saveFile()
            if not ret[0]:
                return StatusInfo(206, f"problem during service move save", ret[1])
        logger.debug(":do_service: .. emission positions ..")
        emit = Emit(move)
        ret = emit.emit(emit_rate)
        if not ret[0]:
            return StatusInfo(207, f"problem during service emission", ret[1])

        service_duration = this_service.duration()

        logger.debug(f":do_flight: .. service duration {service_duration} ..")
        emit.addToPause(SERVICE_PHASE.SERVICE_START.value, service_duration)
        # will trigger new call to emit.emit(emit_rate) to adjust

        logger.debug(":do_service: .. scheduling broadcast ..")
        # default is to serve at scheduled time
        logger.debug(emit.getMarkList())
        logger.debug(f":do_flight: .. {SERVICE_PHASE.SERVICE_START.value} at {scheduled} ..")
        ret = emit.schedule(SERVICE_PHASE.SERVICE_START.value, scheduled_dt)
        if not ret[0]:
            return StatusInfo(208, f"problem during service scheduling", ret[1])
        if SAVE_TO_FILE:
            ret = emit.saveFile()
            if not ret[0]:
                return StatusInfo(209, f"problem during service emission save", ret[1])
        ret = emit.save(redis=self.redis)
        if not ret[0]:
            return StatusInfo(210, f"problem during service emission save to Redis", ret[1])

        logger.debug(":do_service: .. broadcasting position ..")
        formatted = EnqueueToRedis(emit=emit, queue=self.queues[queue], redis=self.redis)
        ret = formatted.format()
        if not ret[0]:
            return StatusInfo(211, f"problem during service formatting", ret[1])
        ret = formatted.save(overwrite=True)
        if not ret[0] and ret[1] != "EnqueueToRedis::save key already exist":
            return StatusInfo(212, f"problem during service save", ret[1])
        ret = formatted.enqueue()
        if not ret[0]:
            return StatusInfo(213, f"problem during service save to Redis", ret[1])

        logger.debug(":do_service: ..done")

        return StatusInfo(0, "completed successfully", this_service.getId())


    def do_flight_services(self, emit_rate, queue, operator, flight_id, estimated = None):
        # @todo: take estimated into account, reschedule accordingly.
        emit_ident = key_path(REDIS_DATABASE.FLIGHTS.value, flight_id, REDIS_TYPE.EMIT.value)
        logger.debug(f":do_flight_services: servicing {emit_ident}..")
        # Get flight data
        logger.debug(":do_flight_services: ..retrieving flight..")
        emit = ReEmit(emit_ident, self.redis)
        emit.setManagedAirport(self)

        scheduled = emit.getMeta("$.move.scheduled")
        if scheduled is None:
            logger.warning(f":do_flight_services: cannot get flight scheduled time {emit.getMeta()}")
            return StatusInfo(250, "cannot get flight scheduled time from meta", emit_ident)

        emit_time_str = estimated if estimated is not None else scheduled
        scheduled = datetime.fromisoformat(scheduled)

        # this is currently unused
        emit_time_dt = datetime.fromisoformat(emit_time_str)
        if emit_time_dt.tzname() is None:  # has no time zone, uses local one
            emit_time_dt = emit_time_dt.replace(tzinfo=self.timezone)
            logger.debug(":do_flight_services: estimated time has no time zone, added managed airport local time zone")

        is_arrival = emit.getMeta("$.move.is_arrival")
        if is_arrival is None:
            logger.warning(f":do_flight_services: cannot get flight movement")
        if is_arrival:
            sync = FLIGHT_PHASE.TOUCH_DOWN.value
            svc_sync = FLIGHT_PHASE.ONBLOCK.value
        else:
            sync = FLIGHT_PHASE.TAKE_OFF.value
            svc_sync = FLIGHT_PHASE.OFFBLOCK.value
        st = emit.getRelativeEmissionTime(sync)
        bt = emit.getRelativeEmissionTime(svc_sync)  # 0 for departure...
        td = bt - st
        blocktime = scheduled + timedelta(seconds=td)

        operator = self.airport.manager.getCompany(operator)

        flight_meta = emit.getMeta("$.move.flight")

        # Need to create a flight container with necessary data
        logger.debug(":do_flight_services: Creating flight shell ..")
        logger.debug(f":do_flight_services: ..is {'arrival' if is_arrival else 'departure'}..")
        airline_code = emit.getMeta("$.move.airline.iata")
        logger.debug(f":do_flight_services: ..got airline code {airline_code}..")
        airline = Airline.find(airline_code, self.redis)
        airport_code = None
        if is_arrival:
            airport_code = emit.getMeta("$.move.departure.airport.icao")
        else:
            airport_code = emit.getMeta("$.move.arrival.airport.icao")
        logger.debug(f":do_flight_services: ..got remote airport code {airport_code}..")
        remote_apt = Airport.find(airport_code, self.redis)
        actype_code = emit.getMeta("$.move.aircraft.actype.base-type.actype")
        logger.debug(f":do_flight_services: ..got actype code {actype_code}..")
        acperf = AircraftPerformance.find(icao=actype_code, redis=self.use_redis())
        acperf.load()
        acreg  = emit.getMeta("$.move.aircraft.acreg")
        icao24 = emit.getMeta("$.move.aircraft.icao24")
        logger.debug(f":do_flight_services: ..got aircraft {acreg}, {icao24}..")
        aircraft = Aircraft(registration=acreg, icao24= icao24, actype=acperf, operator=airline)
        flightnumber = emit.getMeta("$.move.flightnumber")
        logger.debug(f":do_flight_services: ..got flight number {flightnumber}..")
        flight = None
        if is_arrival:
            flight = Arrival(operator=airline,
                             number=flightnumber,
                             scheduled=scheduled,
                             managedAirport=self,
                             origin=remote_apt,
                             aircraft=aircraft)
        else:
            flight = Departure(operator=airline,
                               number=flightnumber,
                               scheduled=scheduled,
                               managedAirport=self,
                               destination=remote_apt,
                               aircraft=aircraft)
        rampcode = emit.getMeta("$.move.ramp.name")
        logger.debug(f":do_flight_services: ..got ramp {rampcode}..")
        rampval = self.airport.getRamp(rampcode, redis=self.use_redis())
        if rampval is None:
            logger.warning(f":do_flight_services: ramp {ramp} not found, quitting")
            return StatusInfo(102, f"ramp {ramp} not found", None)
        flight.setRamp(rampval)
        logger.debug(":do_flight_services: .. done")
        # we "just need" actype and ramp
        logger.debug(f":do_flight_services: got flight: {flight.getInfo()}")

        flight_service = FlightServices(flight, operator)
        flight_service.setManagedAirport(self.airport)
        ret = flight_service.service()
        if not ret[0]:
            return StatusInfo(150, f"problem during flight service", ret[1])

        logger.debug(":do_flight_services: .. moving service vehicle ..")
        ret = flight_service.move()
        if not ret[0]:
            return StatusInfo(151, f"problem during flight service movement creation", ret[1])

        logger.debug(":do_flight_services: .. emiting positions service vehicle ..")
        ret = flight_service.emit(emit_rate)
        if not ret[0]:
            return StatusInfo(152, f"problem during flight service emission", ret[1])

        logger.debug(":do_flight_services: .. scheduling service vehicle ..")
        ret = flight_service.schedule(blocktime)
        if not ret[0]:
            return StatusInfo(153, f"problem during flight service scheduling", ret[1])

        logger.debug(":do_flight_services: .. saving service vehicle ..")
        if SAVE_TO_FILE:
            ret = flight_service.saveFile()
            if not ret[0]:
                return StatusInfo(154, f"problem during flight service scheduling", ret[1])
        ret = flight_service.save(redis=self.redis)
        if not ret[0]:
            return StatusInfo(155, f"problem during flight service save in Redis", ret[1])

        logger.debug(":do_flight_services: .. broadcasting positions ..")
        ret = flight_service.enqueuetoredis(self.queues[queue])
        if not ret[0]:
            return StatusInfo(156, f"problem during enqueue of services", ret[1])

        self.airport.manager.saveAllocators(self.redis)

        logger.debug(":do_flight_services: ..done")
        return StatusInfo(0, "completed successfully", emit.getId())


    def do_mission(self, emit_rate, queue, operator, checkpoints, mission, vehicle_ident, vehicle_icao24, vehicle_model, vehicle_startpos, vehicle_endpos, scheduled):
        logger.debug(":do_mission: creating mission..")
        if len(checkpoints) == 0:
            k = 3
            checkpoints = [c[0] for c in random.choices(self.airport.getCheckpointCombo(), k=k)]  # or getPOICombo()
            logger.debug(f":do_flight_services: ..no checkpoint, generating {k} random checkpoint ({checkpoints})..")

        operator = self.airport.manager.getCompany(operator)
        mission = Mission(operator=operator, checkpoints=checkpoints, name=mission)

        mission_time = datetime.fromisoformat(scheduled)
        if mission_time.tzname() is None:  # has no time zone, uses local one
            mission_time = mission_time.replace(tzinfo=self.timezone)
            logger.debug(":do_mission: scheduled time has no time zone, added managed airport local time zone")

        logger.debug(":do_mission: .. vehicle ..")
        mission_vehicle = self.airport.manager.selectServiceVehicle(operator=operator, service=mission, reqtime=mission_time, model=vehicle_model, registration=vehicle_ident, use=True)
        if mission_vehicle is None:
            return StatusInfo(311, f"connot find vehicle {vehicle_model}", None)
        mission_vehicle.setICAO24(vehicle_icao24)

        logger.debug(":do_mission: .. start and end positions ..")
        start_pos = self.airport.getPOIFromCombo(vehicle_startpos)
        if start_pos is None:
            return StatusInfo(300, f"connot find start position {vehicle_startpos}", None)
        mission_vehicle.setPosition(start_pos)
        end_pos = self.airport.getPOIFromCombo(vehicle_endpos)
        if end_pos is None:
            return StatusInfo(301, f"connot find end position {vehicle_endpos}", None)
        mission_vehicle.setNextPosition(end_pos)

        # logger.debug(":do_mission: ..running..")
        # mission.run()  # do nothing...

        logger.debug(":do_mission: .. moving ..")
        move = MissionMove(mission, self.airport)
        ret = move.move()
        if not ret[0]:
            return StatusInfo(302, f"problem during mission move", ret[1])
        if SAVE_TO_FILE:
            ret = move.saveFile()
            if not ret[0]:
                return StatusInfo(303, f"problem during mission move save", ret[1])

        logger.debug(":do_mission: .. emiting positions ..")
        emit = Emit(move)
        ret = emit.emit(emit_rate)
        if not ret[0]:
            return StatusInfo(304, f"problem during mission emission", ret[1])

        logger.debug(":do_mission: .. scheduling broadcast ..")
        logger.debug(emit.getMarkList())
        ret = emit.schedule(MISSION_PHASE.START.value, mission_time)
        if not ret[0]:
            return StatusInfo(305, f"problem during mission scheduling", ret[1])
        if SAVE_TO_FILE:
            ret = emit.saveFile()
            if not ret[0]:
                return StatusInfo(306, f"problem during mission emission save", ret[1])
        logger.debug(":do_mission: .. saving ..")
        ret = emit.save(redis=self.redis)
        if not ret[0]:
            return StatusInfo(307, f"problem during service mission save to Redis", ret[1])

        logger.debug(":do_mission: .. broadcasting position ..")
        formatted = EnqueueToRedis(emit=emit, queue=self.queues[queue], redis=self.redis)
        logger.debug(":do_mission: .. formatting ..")
        ret = formatted.format()
        if not ret[0]:
            return StatusInfo(308, f"problem during service formatting", ret[1])

        logger.debug(":do_mission: .. saving ..")
        ret = formatted.save(overwrite=True)
        if not ret[0] and ret[1] != "EnqueueToRedis::save key already exist":
            return StatusInfo(309, f"problem during service save", ret[1])
        logger.debug(":do_mission: .. enqueueing for broadcast ..")
        ret = formatted.enqueue()
        if not ret[0]:
            return StatusInfo(310, f"problem during service save to Redis", ret[1])

        logger.debug(":do_mission: ..done")
        return StatusInfo(0, "do_mission completed successfully", mission.getId())


    def do_schedule(self, queue, ident, sync, scheduled, do_services: bool = False):
        emit = ReEmit(ident, self.redis)
        emit.setManagedAirport(self)
        # logger.debug(f":do_flight_services: do_schedule:mark list: {emit.getMarkList()}")
        emit_time = datetime.fromisoformat(scheduled)
        if emit_time.tzname() is None:  # has no time zone, uses local one
            emit_time = emit_time.replace(tzinfo=self.timezone)
            logger.debug(":do_schedule: scheduled time has no time zone, added managed airport local time zone")

        logger.debug(":do_schedule: scheduling ..")
        ret = emit.schedule(sync, emit_time)
        if not ret[0]:
            return StatusInfo(400, f"problem during rescheduling", ret[1])

        logger.debug(":do_schedule: .. broadcasting positions ..")
        formatted = EnqueueToRedis(emit=emit, queue=self.queues[queue], redis=self.redis)
        ret = formatted.format()
        if not ret[0]:
            return StatusInfo(401, f"problem during rescheduled formatting", ret[1])

        logger.debug(":do_schedule: .. saving ..")
        ret = formatted.save(overwrite=True)
        if not ret[0]:
            return StatusInfo(402, f"problem during rescheduled save", ret[1])

        logger.debug(":do_schedule: .. enqueueing for broadcast ..")
        ret = formatted.enqueue()
        if not ret[0]:
            return StatusInfo(403, f"problem during rescheduled enqueing", ret[1])
        logger.debug(":do_schedule: .. done.")


        if not do_services:
            return StatusInfo(0, "scheduled successfully", ident)

        logger.debug(f":do_schedule: doing scheduling of associated services..")
        services = self.airport.manager.allServiceForFlight(redis=self.redis, flight_id=ident)

        is_arrival = emit.getMeta("$.move.is_arrival")
        logger.debug(f":do_schedule: ..is {'arrival' if is_arrival else 'departure'}..")
        if is_arrival:
            svc_sync = FLIGHT_PHASE.ONBLOCK.value
        else:
            svc_sync = FLIGHT_PHASE.OFFBLOCK.value
        blocktime1 = emit.getAbsoluteEmissionTime(svc_sync)
        blocktime = datetime.fromtimestamp(blocktime1)
        logger.debug(f":do_schedule: ..{svc_sync} at {blocktime} ({blocktime1}).. done")

        logger.debug(f":do_schedule: scheduling..")
        for service in services:
            logger.debug(f":do_schedule: ..doing service {service}..")
            k = key_path(service, REDIS_TYPE.EMIT.value)
            se = ReEmit(k, self.redis)
            se.setManagedAirport(self)
            se_relstart = se.getMeta("$.move.ground-support.schedule")
            se_absstart = blocktime + timedelta(minutes=se_relstart)
            logger.debug(f":do_schedule: ..service {service} will start at {se_absstart} {se_relstart}min relative to blocktime {blocktime}..")
            self.do_schedule(queue=queue, ident=k, sync=SERVICE_PHASE.START.value,
                             scheduled=se_absstart.isoformat(), do_services=False)
            # we could cut'n paste code from begining of this function as well...
            # I love recursion.
        logger.debug(f":do_schedule: ..done")

        return StatusInfo(0, "scheduled successfully (with services)", ident)


    def do_delete(self, queue, ident, do_services:bool = False):
        # 1. Delete associated servicse if requested
        if do_services:
            services = self.airport.manager.allServiceForFlight(redis=self.redis, flight_id=ident)
            logger.debug(f":do_delete: deleting services..")
            for service in services:
                logger.debug(f":do_delete: ..{service}..")
                si = self.do_delete(queue, service)
                if si.status != 0:
                    return StatusInfo(501, f"problem during deletion of associated services {service} of {ident} ", si)
            logger.debug(f":do_delete: ..done")

        ret = EnqueueToRedis.delete(ident=ident, queue=queue, redis=self.redis)
        if not ret[0]:
            return StatusInfo(500, f"problem during deletion of {ident} ", ret)

        if do_services:
            return StatusInfo(0, "deleted successfully (with services)", None)

        return StatusInfo(0, "deleted successfully", None)


    def do_create_queue(self, name, formatter, starttime, speed, start: bool):
        """
        Creates or "register" a Queue for (direct) use
        """
        starttime_dt = datetime.fromisoformat(starttime)
        if starttime_dt.tzname() is None:  # has no time zone, uses local one
            starttime_dt = starttime_dt.replace(tzinfo=self.timezone)
            logger.debug(":do_create_queue: starttime time has no time zone, added managed airport local time zone")

        q = Queue(name=name, formatter_name=formatter, starttime=starttime_dt.isoformat(), speed=speed, start=start, redis=self.redis)

        ret = q.save()
        if not ret[0]:
            return StatusInfo(600, f"problem during creation of queue {name} ", ret)
        self.queues[name] = q
        return StatusInfo(0, "queue created successfully", name)


    def do_reset_queue(self, name, starttime, speed, start):
        """
        Reset a queue'start time
        """
        starttime_dt = datetime.fromisoformat(starttime)
        if starttime_dt.tzname() is None:  # has no time zone, uses local one
            starttime_dt = starttime_dt.replace(tzinfo=self.timezone)
            logger.debug(":do_reset_queue: starttime time has no time zone, added managed airport local time zone")

        q = self.queues[name]
        ret = q.reset(speed=speed, starttime=starttime_dt.isoformat(), start=start)
        if not ret[0]:
            return StatusInfo(700, f"problem during restart of queue {name} ", ret)
        return StatusInfo(0, "queue started successfully", name)


    def do_delete_queue(self, name):
        """
        Dlete a Queue
        """
        ret = Queue.delete(redis=self.redis, name=name)
        if not ret[0]:
            return StatusInfo(800, f"problem during deletion of queue {name} ", ret)
        if name in self.queues.keys():
            del self.queues[name]
        return StatusInfo(0, "queue delete successfully", None)


    def do_list_emit(self):
        keys = self.redis.keys(key_path("*", REDIS_TYPE.QUEUE.value))
        karr = [(k.decode("UTF-8"), k.decode("UTF-8")) for k in sorted(keys)]
        return karr


    def do_pias_emit(self, queue, ident):
        ret = EnqueueToRedis.pias(redis=self.redis, ident=ident, queue=queue)
        if not ret[0]:
            return StatusInfo(500, f"problem during pias of {ident}", ret)
        return StatusInfo(0, "pias successfully", None)




