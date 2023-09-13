#
import logging
import json
import random
import time
from datetime import datetime, timedelta, timezone

import redis
# from pottery import RedisDict

import emitpy
from emitpy.managedairport import ManagedAirport
from emitpy.business import Airline, Company, AirportManager
from emitpy.aircraft import AircraftTypeWithPerformance, Aircraft
from emitpy.flight import Arrival, Departure, ArrivalMove, DepartureMove
from emitpy.service import Service, ServiceMovement, FlightServices, Mission, MissionMove
from emitpy.emit import Emit, ReEmit
from emitpy.broadcast import Format, EnqueueToRedis, FormatMessage, EnqueueMessagesToRedis, Queue
# pylint: disable=W0611
from emitpy.constants import SERVICE_PHASE, MISSION_PHASE, FLIGHT_PHASE, FEATPROP, ARRIVAL, LIVETRAFFIC_QUEUE, LIVETRAFFIC_FORMATTER
from emitpy.constants import INTERNAL_QUEUES, ID_SEP, REDIS_TYPE, REDIS_DB, key_path, REDIS_DATABASE, REDIS_PREFIX
from emitpy.constants import MANAGED_AIRPORT_KEY, MANAGED_AIRPORT_LAST_UPDATED, AIRAC_CYCLE
from emitpy.parameters import REDIS_CONNECT, REDIS_ATTEMPTS, REDIS_WAIT, XPLANE_FEED
from emitpy.airport import Airport, AirportWithProcedures, XPAirport
from emitpy.airspace import XPAerospace
from emitpy.weather import XPWeatherEngine, WebWeatherEngine
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


SAVE_TO_FILE = True  # for debugging purpose
SAVE_TRAFFIC = True
LOAD_AIRWAYS = True

def BOOTSTRAP_REDIS():
    NUM_ATTEMPTS = 3
    not_connected = True
    attempts = 0
    logger.debug("BOOTSTRAP_REDIS: connecting to Redis..")
    while not_connected and attempts < REDIS_ATTEMPTS:
        r = redis.Redis(**REDIS_CONNECT)
        try:
            pong = r.ping()
            not_connected = False
            logger.debug("BOOTSTRAP_REDIS: ..connected.")
        except redis.RedisError:
            logger.warning(f"BOOTSTRAP_REDIS: ..cannot connect, retrying ({attempts+1}/{REDIS_ATTEMPTS}, sleeping {REDIS_WAIT} secs)..")
            attempts = attempts + 1
            time.sleep(REDIS_WAIT)

    if not_connected:
        logger.error("BOOTSTRAP_REDIS: ..cannot connect to Redis.")
        return False

    prevdb = r.client_info()["db"]
    r.select(REDIS_DB.REF.value)
    k = key_path(REDIS_PREFIX.AIRPORT.value, MANAGED_AIRPORT_KEY)
    a = r.json().get(k)
    r.select(prevdb)
    logger.debug(f"BOOTSTRAP_REDIS: Managed airport: {json.dumps(a, indent=2)}")
    return a is not None and MANAGED_AIRPORT_LAST_UPDATED in a and AIRAC_CYCLE in a


class EmitApp(ManagedAirport):

    def __init__(self, icao):

        self.redis_pool = None
        self.redis = None
        self.gas = None

        self._use_redis = BOOTSTRAP_REDIS()
        if self._use_redis:
            self.init_redis(icao)

        # Here we set the "flavor" of main class we will use for the generation
        # (there are currently, no other flavors... :-D )
        self._aerospace = XPAerospace
        self._managedairport = XPAirport
        self._airportmanager = AirportManager
        self._weather_engine = WebWeatherEngine # XPWeatherEngine

        ManagedAirport.__init__(self, icao=icao, app=self)

        self.local_timezone = datetime.now(timezone.utc).astimezone().tzinfo

        # If Redis is defined before calling init(), it will use it.
        # Otherwise, it will use the data files.
        if self._use_redis:
            logger.info(f"using Redis")
            # Prepare default queue(s)
            self.redis.select(REDIS_DB.APP.value)
            self.queues = Queue.loadAllQueuesFromDB(self.redis)
            # logger.debug("checking for default queues..")
            for k, v in INTERNAL_QUEUES.items():
                if k not in self.queues.keys():
                    logger.debug(f"creating missing default queue {k}..")
                    self.queues[k] = Queue(name=k, formatter_name=v, redis=self.redis)
                    self.queues[k].save()

            if XPLANE_FEED:  # obstinately harcoded
                k = LIVETRAFFIC_QUEUE
                v = LIVETRAFFIC_FORMATTER
                if k not in self.queues.keys():
                    logger.debug(f"creating LiveTraffic queue with {LIVETRAFFIC_FORMATTER} formatter")
                    self.queues[k] = Queue(name=k, formatter_name=v, redis=self.redis)
                    self.queues[k].save()
        else:
            logger.info(f"not using Redis")

        ret = self.init(load_airways=LOAD_AIRWAYS)
        if not ret[0]:
            logger.warning(ret[1])
            return

        ret = self.loadFromCache()
        if not ret[0]:
            logger.warning(ret[1])
            return

        logger.debug("initialized. listening.."+ "\n\n")
        # logger.warning("=" * 90)


    def init_redis(self, icao):
        # (Mandatory) use of Redis starts here
        # Redis is sometimes slow to start, wait for it a bit
        not_connected = True
        attempts = 0
        while not_connected and attempts < 10:
            self.redis_pool = redis.ConnectionPool(**REDIS_CONNECT)
            self.redis = redis.Redis(connection_pool=self.redis_pool)
            try:
                pong = self.redis.ping()
                not_connected = False
                logger.info("connected to Redis")
                self.redis.config_set('notify-keyspace-events', "KA")
                logger.debug(f"{self.redis.config_get('notify-keyspace-events')}")
                logger.info("keyspace notification enabled")
            except redis.RedisError:
                logger.error("cannot connect to redis, retrying...")
                attempts = attempts + 1
                time.sleep(2)
        if not_connected:
            logger.error("cannot connect to redis")
            return
        ret = self.check_data(icao)
        if not ret[0]:
            logger.error(ret[1])
            exit(1)
        # Init "Global Airport Status" structure.
        # For later use. Used for testing only.
        # self.redis.select(REDIS_DB.CACHE.value)
        # self.gas = RedisDict(None, redis=redis.Redis(connection_pool=self.redis_pool), key='airport')
        # self.gas["managed-airport"] = airport
        # self.redis.select(REDIS_DB.APP.value)


    def use_redis(self):
        """
        Function that check whether we are using Redis for data.
        If true, we return a redis connection instance ready to be used.
        If false, we return None and the function that called us can choose another path.
        """
        if self._use_redis:
            return redis.Redis(connection_pool=self.redis_pool)
        return None


    def check_data(self, icao):
        prevdb = self.redis.client_info()["db"]
        self.redis.select(REDIS_DB.REF.value)
        k = key_path(REDIS_PREFIX.AIRPORT.value, MANAGED_AIRPORT_KEY)
        a = self.redis.json().get(k)
        self.redis.select(prevdb)
        logger.info(f"check_data: found managed airport in Redis: {json.dumps(a, indent=2)}")
        if a is not None:
            if a["ICAO"] != icao:
                return (False, f"EmitApp::check_data: airport '{a['ICAO']}' in Redis does not match managed airport '{icao}'")
            if MANAGED_AIRPORT_LAST_UPDATED in a and AIRAC_CYCLE in a:
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
        logger.debug("saving .. (this may take a few microseconds)")
        self.airport.manager.saveAllocators(self.redis)
        logger.debug("..done")


    def loadFromCache(self):
        logger.debug("loading .. (this may take a few microseconds)")
        self.airport.manager.loadAllocators(self.redis)
        logger.debug("..done")
        return (True, "EmitApp::loadFromCache: loaded")


    def shutdown(self):
        logger.debug("..shutting down..")
        self.saveToCache()
        logger.debug("..done")

    # #####################################################
    # Steps in do_ methods:
    #
    # 0. Presentation + input
    # 1. Collect data
    # 2. Present collected data
    # 3. Create flight/mission/service...
    # 4. Create move
    # 5. (save move?)
    # 6. Create emit
    # 7. Schedule emit
    # 8. Schedule messages
    # 9. (save emit?)
    # 10. (save messages?)
    # 11. Create format + format position
    # 12. (save formatted positions)
    # 13. Enqueue positions
    # 14. Create format + format messages
    # 15. (save formatted messages)
    # 16. Enqueue messages
    # 17. Done + summary
    #
    #

    def do_flight(self, queue, emit_rate, airline, flightnumber, scheduled, apt, movetype, actype, ramp, icao24, acreg, runway: str = None, load_factor:float = 1.0, is_cargo: bool = False, do_services: bool = False, actual_datetime: str = None):
        # 0. Presentation + input
        fromto = "from" if movetype == ARRIVAL else "to"
        logger.info("*" * 110)
        logger.info(f"***** {airline}{flightnumber} {scheduled} {movetype} {fromto} {apt} {actype} {icao24} {acreg} {ramp} {runway}")
        logger.debug(f"**** scheduled {FLIGHT_PHASE.TOUCH_DOWN.value if movetype == ARRIVAL else FLIGHT_PHASE.TAKE_OFF.value} {actual_datetime if actual_datetime is not None else scheduled}")
        logger.debug("*" * 109)

        emit_rate_svc = emit_rate
        if type(emit_rate) in [list, tuple]:
            emit_rate_svc = emit_rate[1]
            emit_rate = emit_rate[0]
            logger.debug(f"emit rates: flights: {emit_rate}, services: {emit_rate_svc}")

        # 1. Collecting data
        logger.debug("collecting data for flight..")
        logger.debug("..airline..")
        # Add pure commercial stuff
        airline = Airline.find(airline, self.redis)
        if airline is None:
            logger.error("airline not found")
            return StatusInfo(1, "error", None)

        logger.debug("..remote airport..")
        remote_apt = Airport.find(apt, self.redis)
        if remote_apt is None:
            logger.error("remote airport not found")
            return StatusInfo(2, "error", None)

        aptrange = self.airport.miles(remote_apt)

        logger.debug("..remote airport with procedures..")
        remote_apt = AirportWithProcedures.new(remote_apt)  # @todo: ManagedAirportBase
        logger.debug(f"remote airport is {remote_apt}")

        # if self._use_redis:
        #     prevdb = self.redis.client_info()["db"]
        #     self._app.redis.select(1)
        #     remote_apt.save("airports", self.use_redis())
        #     self._app.redis.select(prevdb)
        #     logger.debug(f"remote airport saved")
        logger.debug("..setting scheduled date/time..")
        scheduled_dt = datetime.fromisoformat(scheduled)
        if scheduled_dt.tzname() is None:  # has no time zone, uses local one
            scheduled_dt = scheduled_dt.replace(tzinfo=self.timezone)
            logger.debug("scheduled time has no time zone, added managed airport local time zone")

        logger.debug("..collecting weather for remote airport..")
        dt2 = datetime.now().astimezone(self.timezone) - timedelta(days=1)
        if scheduled_dt < dt2:
            remote_apt.updateWeather(weather_engine=self.weather_engine, moment=scheduled_dt) 
        else:
            remote_apt.updateWeather(weather_engine=self.weather_engine) 

        logger.debug("..loading aircraft type..")
        acarr = (actype, actype) if type(actype) == str else actype
        actype, acsubtype = acarr
        ac = AircraftTypeWithPerformance.findAircraftByType(actype, acsubtype, self.use_redis())
        if ac is None:
            return StatusInfo(3, f"aircraft performance not found for {actype} or {acsubtype}", None)
        acperf = AircraftTypeWithPerformance.find(icao=ac, redis=self.use_redis())
        if acperf is None:
            return StatusInfo(4, f"aircraft performance not found for {ac}", None)
        acperf.load()
        reqfl = acperf.FLFor(aptrange)

        logger.debug("..loading aircraft..")
        aircraft = Aircraft(registration=acreg, icao24= icao24, actype=acperf, operator=airline)
        aircraft.save(self.redis)
        logger.debug("..done collecting data for flight")

        # 2. Present collected data
        # logger.info("*" * 90)
        logger.info("***** (%s, %dnm) %s-%s AC %s at FL%d" % (
                    remote_apt.getProp(FEATPROP.CITY.value), aptrange/NAUTICAL_MILE, remote_apt.iata, self.iata,
                    acperf.typeId, reqfl))
        # logger.debug("*" * 89)

        # 3. Create flight/mission/service...
        logger.debug("creating flight..")
        flight = None
        if movetype == ARRIVAL:
            flight = Arrival(operator=airline,
                             number=flightnumber,
                             scheduled=scheduled_dt,
                             managedAirport=self,
                             origin=remote_apt,
                             aircraft=aircraft,
                             load_factor=load_factor)
            sync = FLIGHT_PHASE.TOUCH_DOWN.value
            svc_sync = FLIGHT_PHASE.ONBLOCK.value
            Movement = ArrivalMove  # Typed
        else:
            flight = Departure(operator=airline,
                               number=flightnumber,
                               scheduled=scheduled_dt,
                               managedAirport=self,
                               destination=remote_apt,
                               aircraft=aircraft,
                               load_factor=load_factor)
            sync = FLIGHT_PHASE.TAKE_OFF.value
            svc_sync = FLIGHT_PHASE.OFFBLOCK.value
            Movement = DepartureMove  # Typed

        # 3.2 Schedule actual time if supplied
        logger.debug(f"scheduled={scheduled}, actual={actual_datetime} ({sync})")
        emit_time_str = actual_datetime if actual_datetime is not None else scheduled
        emit_time = datetime.fromisoformat(emit_time_str)
        if emit_time.tzname() is None:  # has no time zone, uses local one
            emit_time = emit_time.replace(tzinfo=self.timezone)
            logger.debug("actual time has no time zone, added managed airport local time zone")
        flight.setEstimatedTime(emit_time)

        # 3.3 Set details
        if is_cargo:
            flight.set_cargo()

        aircraft.setCallsign(airline.icao+flightnumber)

        if runway is not None and runway != "":
            self.airport.setRunwaysInUse(runway)
        # else:??

        flight.setFL(reqfl)

        rampval = self.airport.getRamp(ramp, redis=self.use_redis())
        if rampval is None:
            logger.warning(f"ramp {ramp} not found, quitting")
            return StatusInfo(5, f"ramp {ramp} not found", None)
        flight.setRamp(rampval)

        gate = "C99"
        # this is special for OTHH
        ramp_name = rampval.getName()
        if ramp_name[0] in "A,B,C,D,E".split(",") and len(ramp) < 5:  # does now work for "Cargo Ramp F5" ;-)
            gate = ramp_name
        flight.setGate(gate)

        # 3.4 planning + route
        logger.debug("..planning..")
        ret = flight.plan()
        if not ret[0]:
            return StatusInfo(6, f"problem during flight planning", ret[1])

        logger.debug(f"route: {flight.printFlightRoute()}")
        logger.debug(f"plan : {flight.printFlightPlan()}")

        # 4. Move
        # 4.1 Create move
        logger.debug("..flying..")
        move = Movement(flight, self.airport)  # Typed, see flight creation
        ret = move.move()
        if not ret[0]:
            return StatusInfo(7, f"problem during move", ret[1])

        # 4.2 Save move
        # move.save()

        # 6. Create emit
        logger.debug("..emitting..")
        emit = Emit(move)
        ret = emit.emit(emit_rate)
        if not ret[0]:
            return StatusInfo(8, f"problem during emit", ret[1])

        # 7. Schedule emit
        logger.debug("..scheduling..")
        ret = emit.schedule(sync, emit_time, do_print=True)
        if not ret[0]:
            return StatusInfo(9, f"problem during schedule", ret[1])

        # 8. Schedule messages
        ret = emit.scheduleMessages(sync, emit_time, do_print=True)
        if not ret[0]:
            return StatusInfo(10, f"problem during schedule of messages", ret[1])

        # 9. (save emit?)
        if SAVE_TO_FILE or SAVE_TRAFFIC:
            logger.debug("..saving positions to file..")
            ret = emit.saveFile()
            if not ret[0]:
                return StatusInfo(11, f"problem during save to file", ret[1])

        if self._use_redis:
            logger.debug("..saving positions to Redis..")
            ret = emit.save(redis=self.redis)
            if not ret[0]:
                return StatusInfo(12, f"problem during save to Redis", ret[1])

        # 10. (save messages?)


        # 11. Create format + format positions
        logger.debug("..broadcasting positions..")
        formatted = None
        if self._use_redis:
            logger.debug("..preparing formatter for redis..")
            formatted = EnqueueToRedis(emit=emit, queue=self.queues[queue], redis=self.redis)
        else:
            logger.debug("..preparing formatter..")
            formatted = Format(emit=emit)

        if formatted is None:
            return StatusInfo(13, f"problem during preparation of formatting of positions", ret[1])

        logger.debug("..formatting..")
        ret = formatted.format()
        if not ret[0]:
            return StatusInfo(14, f"problem during formatting of positions", ret[1])

        # 12. (save formatted position)
        if self._use_redis:
            logger.debug("..saving formatted position to Redis..")
            ret = formatted.save(overwrite=True)
            if not ret[0]:
                return StatusInfo(15, f"problem during save of positions to Redis", ret[1])

        if SAVE_TO_FILE:
            logger.debug("..saving formatted position to file..")
            ret = formatted.saveFile()
            # Redis: "EnqueueToRedis::save key already exist"
            # File:  "Format::save file already exist"
            if not ret[0] and not ret[1].endswith("already exist"):
                return StatusInfo(16, f"problem during formatted position output save", ret[1])

        # 13. Enqueue positions
        if self._use_redis:
            logger.debug("..enqueuing positions to Redis..")
            ret = formatted.enqueue()
            if not ret[0]:
                return StatusInfo(17, f"problem during enqueue of positions to Redis", ret[1])

        # 14. Create format + format messages
        logger.debug("..broadcasting messages..")
        formatted_message = None
        if self._use_redis:
            formatted_message = EnqueueMessagesToRedis(emit=emit, queue=self.queues["wire"], redis=self.redis)
        else:
            formatted_message = FormatMessage(emit=emit)

        if formatted_message is None:
            return StatusInfo(18, f"problem during formatting of messages", ret[1])

        logger.debug("..formatting messages..")
        ret = formatted_message.format()
        if not ret[0]:
            return StatusInfo(19, f"problem during formatting of messages", ret[1])

        # 15. (save formatted messages)
        if SAVE_TO_FILE:
            logger.debug("..saving messages to file..")
            ret = formatted_message.saveFile(overwrite=True)
            # Redis: "EnqueueToRedis::save key already exist"
            # File:  "Format::save file already exist"
            if not ret[0] and not ret[1].endswith("already exist"):
                return StatusInfo(20, f"problem during formatted message output save", ret[1])

        # 16. Enqueue messages
        if self._use_redis:
            logger.debug("..enqueuing messages to Redis..")
            ret = formatted_message.enqueue()
            if not ret[0]:
                return StatusInfo(21, f"problem during enqueue of messages", ret[1])

        # 17. Done + summary
        logger.info("***** SAVED " + ("*" * 87))

        if not do_services:
            logger.debug("..done")
            return StatusInfo(0, "completed successfully", flight.getId())

        # 0. Presentation + input
        logger.debug("*" * 110)
        logger.debug(f"**** {airline.iata}{flightnumber} {scheduled} {movetype} {fromto} {apt} {actype} {icao24} {acreg} {ramp} {runway}")
        logger.debug(f"* done schedule {FLIGHT_PHASE.TOUCH_DOWN.value if movetype == ARRIVAL else FLIGHT_PHASE.TAKE_OFF.value} {actual_datetime if actual_datetime is not None else scheduled}")

        # 1. Collect data
        logger.debug("collecting data for flight services..")

        st = emit.getRelativeEmissionTime(sync)
        if st is None:
            logger.warning(f"could not collect {sync} time, cannot schedule services..")
            return StatusInfo(1, "could not find sync", flight.getId())

        bt = emit.getRelativeEmissionTime(svc_sync)  # 0 for departure...
        if bt is None:
            logger.warning(f"could not collect {svc_sync} time, cannot schedule services..")
            return StatusInfo(1, "could not find service sync", flight.getId())

        td = bt - st
        blocktime = emit_time + timedelta(seconds=td)

        logger.info(f"**** {airline.iata}{flightnumber} Services scheduled {FLIGHT_PHASE.ONBLOCK.value if movetype == ARRIVAL else FLIGHT_PHASE.OFFBLOCK.value} {blocktime}")
        logger.debug("*" * 109)

        # @todo: pass service operator
        operator = Company(orgId="Airport Operator", classId="Airport Operator", typeId="Airport Operator", name=self.operator)
        # operator = self.airport.manager.getCompany(operator)
        logger.debug(".. done collecting data for flight services")

        # 2. Present collected data
        # 3. Create flight/mission/service...
        logger.debug("creating flight services..")
        flight_service = FlightServices(flight, operator)
        flight_service.setManagedAirport(self)
        ret = flight_service.service()
        if not ret[0]:
            return StatusInfo(21, f"problem during flight service", ret[1])

        # 4. Create move
        logger.debug("..moving equipment..")
        ret = flight_service.move()
        if not ret[0]:
            return StatusInfo(22, f"problem during flight service movement creation", ret[1])

        # 5. (save move?)
        # 6. Create emit
        logger.debug("..emitting equipment positions..")
        ret = flight_service.emit(emit_rate_svc)
        if not ret[0]:
            return StatusInfo(23, f"problem during flight service emission", ret[1])

        # 7. Schedule emit
        logger.debug("..scheduling equipment..")
        ret = flight_service.schedule(blocktime, do_print=True)
        if not ret[0]:
            return StatusInfo(24, f"problem during flight service scheduling", ret[1])

        # 8. Schedule messages
        logger.debug("..scheduling messages..")
        ret = flight_service.scheduleMessages(blocktime, do_print=True)
        if not ret[0]:
            return StatusInfo(25, f"problem during flight service scheduling of messages", ret[1])

        # 9. (save emit?)
        # 10. (save messages?)
        if SAVE_TO_FILE or SAVE_TRAFFIC:
            logger.debug("..saving equipment and messages to files..")
            ret = flight_service.saveFile()
            if not ret[0]:
                return StatusInfo(26, f"problem during flight service scheduling", ret[1])

        if self._use_redis:
            logger.debug("..saving equipment and messages to Redis..")
            ret = flight_service.save(redis=self.redis)
            if not ret[0]:
                return StatusInfo(27, f"problem during flight service save in Redis", ret[1])

        # 11. Create format + format position
        # 12. (save formatted positions)
        # 13. Enqueue positions
        logger.debug("..broadcasting positions..")
        if self._use_redis:
            logger.debug("..enqueuing flight services positions to Redis..")
            ret = flight_service.enqueueToRedis(self.queues[queue])  # also enqueues...
            if not ret[0]:
                return StatusInfo(28, f"problem during enqueue of services", ret[1])

        # 14. Create format + format messages
        # 15. (save formatted messages)
        # 16. Enqueue messages
            logger.debug("..broadcasting messages..")
            logger.debug("..enqueue of flight services messages to Redis..")
            ret = flight_service.enqueueMessagesToRedis(self.queues["wire"])  # also enqueues...
            if not ret[0]:
                return StatusInfo(29, f"problem during enqueue of services", ret[1])

            logger.debug("..saving allocations to Redis..")
            self.airport.manager.saveAllocators(self.redis)

        else:
            logger.debug("..formatting services..")
            ret = flight_service.format(saveToFile=SAVE_TO_FILE or SAVE_TRAFFIC)
            if not ret[0] and not ret[1].endswith("already exist"):
                return StatusInfo(30, f"problem during formating", ret[1])
            # @todo: save to file?

        # 17. Done + summary
        logger.info("***** SERVICED " + ("*" * 83))
        logger.debug("..done, service included.")
        return StatusInfo(0, "completed successfully", flight.getId())


    def do_service(self, queue, emit_rate, operator, service, quantity, ramp, aircraft, equipment_ident, equipment_icao24, equipment_model, equipment_startpos, equipment_endpos, scheduled):
        # Steps in do_ methods.
        # 0. Presentation + input
        # 1. Collect data
        logger.debug("collecting data for service..")
        logger.debug("..aircraft type..")
        acperf = AircraftTypeWithPerformance.find(aircraft, redis=self.use_redis())
        if acperf is None:
            return StatusInfo(31, f"EmitApp:do_service: aircraft performance {aircraft} not found", None)
        acperf.load()

        logger.debug("..service operator..")
        operator = Company(orgId="Airport Operator", classId="Airport Operator", typeId="Airport Operator", name=self.operator)

        logger.debug(f"..done collecting data for service")

        # 2. Present collected data
        # 3. Create flight/mission/service...
        logger.debug("creating service..")
        rampval = self.airport.getRamp(ramp, redis=self.use_redis())
        if rampval is None:
            return StatusInfo(32, f"EmitApp:do_service: ramp {ramp} not found", None)
        scheduled_dt = datetime.fromisoformat(scheduled)
        if scheduled_dt.tzname() is None:  # has no time zone, uses local one
            scheduled_dt = scheduled_dt.replace(tzinfo=self.timezone)
            logger.debug("scheduled time has no time zone, added managed airport local time zone")
        this_service = Service.getService(service)(scheduled=scheduled_dt,
                                                   ramp=rampval,
                                                   operator=operator,
                                                   quantity=quantity)
        this_service.setAircraftType(acperf)
        logger.debug("..finding equipment..")
        this_equipment = self.airport.manager.selectEquipment(operator=operator, service=this_service, reqtime=scheduled_dt, model=equipment_model, registration=equipment_ident, use=True)
        if this_equipment is None:
            return StatusInfo(33, f"EmitApp:do_service: vehicle not found", None)
        this_equipment.setICAO24(equipment_icao24)
        startpos = self.airport.selectServicePOI(equipment_startpos, service, redis=self.use_redis())
        if startpos is None:
            return StatusInfo(34, f"EmitApp:do_service: start position {equipment_startpos} for {service} not found", None)
        this_equipment.setPosition(startpos)  # this is the start position for the vehicle
        nextpos = self.airport.selectServicePOI(equipment_endpos, service, redis=self.use_redis())
        if nextpos is None:
            return StatusInfo(35, f"EmitApp:do_service: start position {equipment_endpos} for {service} not found", None)
        this_equipment.setNextPosition(nextpos)  # this is the position the vehicle is going to after service

        # 4. Create move
        logger.debug("..moving..")
        move = ServiceMovement(this_service, self.airport)
        ret = move.move()
        if not ret[0]:
            return StatusInfo(36, f"problem during service move", ret[1])

        # 5. (save move?)
        if SAVE_TO_FILE:
            ret = move.saveFile()
            if not ret[0]:
                return StatusInfo(37, f"problem during service move save", ret[1])

        # 6. Create emit
        logger.debug("..emitting..")
        emit = Emit(move)
        ret = emit.emit(emit_rate)
        if not ret[0]:
            return StatusInfo(38, f"problem during service emission", ret[1])

        # 7. Schedule emit
        logger.debug("..scheduling positions..")
        # default is to serve at scheduled time
        logger.debug(f"..{SERVICE_PHASE.SERVICE_START.value} at {scheduled}..")
        ret = emit.schedule(SERVICE_PHASE.SERVICE_START.value, scheduled_dt)
        if not ret[0]:
            return StatusInfo(39, f"problem during service scheduling", ret[1])

        # 9. (save emit?)
        if SAVE_TO_FILE:
            logger.debug("..saving positions to file..")
            ret = emit.saveFile()
            if not ret[0]:
                return StatusInfo(40, f"problem during service emission save", ret[1])

        if self._use_redis:
            logger.debug("..saving positions to Redis..")
            ret = emit.save(redis=self.redis)
            if not ret[0]:
                return StatusInfo(41, f"problem during service emission save to Redis", ret[1])

        # 8. Schedule messages
        logger.debug("..scheduling messages..")
        ret = emit.scheduleMessages(sync, emit_time, do_print=True)
        if not ret[0]:
            return StatusInfo(42, f"problem during schedule of messages", ret[1])
        # 10. (save messages?)

        # 11. Create format + format position
        logger.debug("..broadcasting positions..")
        formatted = None
        if self._use_redis:
            logger.debug("..preparation of formatting for Redis..")
            formatted = EnqueueToRedis(emit=emit, queue=self.queues[queue], redis=self.redis)
        else:
            logger.debug("..preparation of formatting..")
            formatted = Format(emit=emit)

        if formatted is None:
            return StatusInfo(43, f"problem during preparation of formatting of positions", ret[1])

        logger.debug("..formatting..")
        ret = formatted.format()
        if not ret[0]:
            return StatusInfo(44, f"problem during formatting of positions", ret[1])


        # 12. (save formatted positions)
        if self._use_redis:
            logger.debug("..save to Redis..")
            ret = formatted.save()
            if not ret[0]:
                return StatusInfo(45, f"problem during service save to Redis", ret[1])
        else:
            logger.debug("..saving to file..")
            ret = formatted.saveFile()
            if not ret[0]:
                return StatusInfo(46, f"problem during service save to file", ret[1])

        # 13. Enqueue positions
        if self._use_redis:
            logger.debug("..enqueue to redis..")
            ret = formatted.enqueue()
            if not ret[0]:
                return StatusInfo(47, f"problem during service enqueue to Redis", ret[1])

        # 14. Create format + format messages
        ## @todo
        # 15. (save formatted messages)
        ## @todo
        # 16. Enqueue messages
        ## @todo

        # 17. Done + summary
        logger.debug("..done")
        return StatusInfo(0, "completed successfully", this_service.getId())


    def do_flight_services(self, emit_rate, queue, operator, flight_id, estimated = None):
        # 0. Presentation + input
        # 1. Collect data

        emit_ident = flight_id
        logger.debug(f"servicing {emit_ident}..")
        # Get flight data
        logger.debug("..retrieving flight..")
        emit = ReEmit(emit_ident, self.redis)
        emit.setManagedAirport(self)

        scheduled = emit.getMeta("$.move.flight.scheduled")
        if scheduled is None:
            logger.warning(f"cannot get flight scheduled time {emit.getMeta()}")
            return StatusInfo(400, "cannot get flight scheduled time from meta", emit_ident)

        emit_time_str = estimated if estimated is not None else scheduled
        scheduled = datetime.fromisoformat(scheduled)

        # this is currently unused
        emit_time_dt = datetime.fromisoformat(emit_time_str)
        if emit_time_dt.tzname() is None:  # has no time zone, uses local one
            emit_time_dt = emit_time_dt.replace(tzinfo=self.timezone)
            logger.debug("estimated time has no time zone, added managed airport local time zone")

        is_arrival = emit.getMeta("$.move.flight.is_arrival")
        if is_arrival is None:
            logger.warning(f"cannot get flight movement")
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
        logger.debug("Creating flight shell..")
        logger.debug(f"..is {'arrival' if is_arrival else 'departure'}..")
        airline_code = emit.getMeta("$.move.flight.airline.iata")
        logger.debug(f"..got airline code {airline_code}..")
        airline = Airline.find(airline_code, self.redis)
        airport_code = None
        if is_arrival:
            airport_code = emit.getMeta("$.move.flight.departure.icao")
        else:
            airport_code = emit.getMeta("$.move.flight.arrival.icao")
        logger.debug(f"..got remote airport code {airport_code}..")
        remote_apt = Airport.find(airport_code, self.redis)
        actype_code = emit.getMeta("$.move.flight.aircraft.actype.base-type.actype")
        logger.debug(f"..got actype code {actype_code}..")
        acperf = AircraftTypeWithPerformance.find(icao=actype_code, redis=self.use_redis())
        acperf.load()
        acreg  = emit.getMeta("$.move.flight.aircraft.acreg")
        icao24 = emit.getMeta("$.move.flight.aircraft.icao24")
        logger.debug(f"..got aircraft {acreg}, {icao24}..")
        aircraft = Aircraft(registration=acreg, icao24= icao24, actype=acperf, operator=airline)
        flightnumber = emit.getMeta("$.move.flight.flightnumber")
        logger.debug(f"..got flight number {flightnumber}..")
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
        rampcode = emit.getMeta("$.move.flight.ramp.name")
        logger.debug(f"..got ramp {rampcode}..")
        rampval = self.airport.getRamp(rampcode, redis=self.use_redis())
        if rampval is None:
            logger.warning(f"ramp {ramp} not found, quitting")
            return StatusInfo(405, f"ramp {ramp} not found", None)
        flight.setRamp(rampval)
        logger.debug("..done")

        # 2. Present collected data
        # we "just need" actype and ramp
        logger.debug(f"got flight: {flight.getInfo()}")


        # 3. Create flight/mission/service...
        flight_service = FlightServices(flight, operator)
        flight_service.setManagedAirport(self)
        logger.debug("..preparing flight service..")
        ret = flight_service.service()
        if not ret[0]:
            return StatusInfo(410, f"problem during preparation of flight service", ret[1])

        # 4. Create move
        logger.debug("..moving equipment..")
        ret = flight_service.move()
        if not ret[0]:
            return StatusInfo(415, f"problem during flight service movement creation", ret[1])

        # 5. (save move?)
        # 6. Create emit
        logger.debug("..emiting equipment positions..")
        ret = flight_service.emit(emit_rate)
        if not ret[0]:
            return StatusInfo(420, f"problem during flight service emission", ret[1])

        # 7. Schedule emit
        logger.debug("..scheduling equipment..")
        ret = flight_service.schedule(blocktime)
        if not ret[0]:
            return StatusInfo(425, f"problem during flight service scheduling", ret[1])

        # 8. Schedule messages
        ## @todo
        # 9. (save emit?)
        logger.debug("..saving equipment..")
        if SAVE_TO_FILE:
            ret = flight_service.saveFile()
            if not ret[0]:
                return StatusInfo(430, f"problem during flight service scheduling", ret[1])
        ret = flight_service.save(redis=self.redis)
        if not ret[0]:
            return StatusInfo(435, f"problem during flight service save in Redis", ret[1])

        # 10. (save messages?)
        ## @todo
        # 11. Create format + format position
        ## @todo
        # 12. (save formatted positions)
        ## @todo
        # 13. Enqueue positions
        if self._use_redis:
            logger.debug("..broadcasting positions..")
            ret = flight_service.enqueueToRedis(self.queues[queue])  # does it all: Formatting, saving, enqueuing
            if not ret[0]:
                return StatusInfo(440, f"problem during enqueue of services", ret[1])

            logger.debug("..saving allocations..")
            self.airport.manager.saveAllocators(self.redis)

        # 14. Create format + format messages
        ## @todo
        # 15. (save formatted messages)
        ## @todo
        # 16. Enqueue messages

        # 17. Done + summary
        logger.debug("..done")
        return StatusInfo(0, "completed successfully", emit.getId())


    def do_turnaround(self, queue, emit_rate, operator, arrival, departure, estimated = None, departure_estimate = None):
        logger.debug(f"do_turnaround: serving arrival..")
        self.do_flight_services(emit_rate=emit_rate,
                                queue=queue,
                                operator=operator,
                                flight_id=arrival,
                                estimated=estimated)
        logger.debug(f"do_turnaround: ..serving departure..")
        self.do_flight_services(emit_rate=emit_rate,
                                queue=queue,
                                operator=operator,
                                flight_id=departure,
                                estimated=departure_estimate)
        logger.debug(f"do_turnaround: .. done")
        return StatusInfo(0, "completed successfully", None)


    def do_mission(self, emit_rate, queue, operator, checkpoints, mission, equipment_ident, equipment_icao24, equipment_model, equipment_startpos, equipment_endpos, scheduled):
        # 0. Presentation + input
        # 1. Collect data
        logger.debug("creating mission..")
        if len(checkpoints) == 0:
            k = 3
            checkpoints = [c[0] for c in random.choices(self.airport.getCheckpointCombo(), k=k)]  # or getPOICombo()
            logger.debug(f"..no checkpoint, generating {k} random checkpoint ({checkpoints})..")
        else:
            logger.debug(f"..visiting checkpoints ({checkpoints})..")

        operator = self.airport.manager.getCompany(operator)
        # 2. Present collected data
        # 3. Create flight/mission/service...
        mission = Mission(operator=operator, checkpoints=checkpoints, name=mission)

        mission_time = datetime.fromisoformat(scheduled)
        if mission_time.tzname() is None:  # has no time zone, uses local one
            mission_time = mission_time.replace(tzinfo=self.timezone)
            logger.debug("scheduled time has no time zone, added managed airport local time zone")

        logger.debug("..vehicle..")
        mission_equipment = self.airport.manager.selectEquipment(operator=operator, service=mission, reqtime=mission_time, model=equipment_model, registration=equipment_ident, use=True)
        if mission_equipment is None:
            return StatusInfo(200, f"connot find vehicle {equipment_model}", None)
        mission_equipment.setICAO24(equipment_icao24)

        logger.debug("..start and end positions..")
        start_pos = self.airport.getPOIFromCombo(equipment_startpos)
        if start_pos is None:
            return StatusInfo(201, f"connot find start position {equipment_startpos}", None)
        mission_equipment.setPosition(start_pos)
        end_pos = self.airport.getPOIFromCombo(equipment_endpos)
        if end_pos is None:
            return StatusInfo(202, f"connot find end position {equipment_endpos}", None)
        mission_equipment.setNextPosition(end_pos)

        # logger.debug("..running..")
        # mission.run()  # do nothing...

        # 4. Create move
        logger.debug("..moving..")
        move = MissionMove(mission, self.airport)
        ret = move.move()
        if not ret[0]:
            return StatusInfo(203, f"problem during mission move", ret[1])
        if SAVE_TO_FILE:
            ret = move.saveFile()
            if not ret[0]:
                return StatusInfo(204, f"problem during mission move save", ret[1])

        # 5. (save move?)
        # 6. Create emit
        logger.debug("..emiting positions..")
        emit = Emit(move)
        ret = emit.emit(emit_rate)
        if not ret[0]:
            return StatusInfo(205, f"problem during mission emission", ret[1])

        # 7. Schedule emit
        logger.debug("..scheduling broadcast..")
        ret = emit.schedule(MISSION_PHASE.START.value, mission_time)
        if not ret[0]:
            return StatusInfo(206, f"problem during mission scheduling", ret[1])

        # 9. (save emit?)
        if SAVE_TO_FILE or SAVE_TRAFFIC:
            logger.debug("..saving to file..")
            ret = emit.saveFile()
            if not ret[0]:
                return StatusInfo(207, f"problem during mission emission save", ret[1])

        if self._use_redis:
            logger.debug("..saving to Redis..")
            ret = emit.save(redis=self.redis)
            if not ret[0]:
                return StatusInfo(208, f"problem during mission mission save to Redis", ret[1])

        # 8. Schedule messages
        logger.debug("..scheduling messages..")
        ret = emit.scheduleMessages(MISSION_PHASE.START.value, mission_time, do_print=True)
        if not ret[0]:
            return StatusInfo(209, f"problem during schedule of messages", ret[1])

        # 10. (save messages?)
        logger.debug("..broadcasting positions..")

        # 11. Create format + format position
        formatted = None
        if self._use_redis:
            logger.debug("..preparing formatting for enqueue to redis..")
            formatted = EnqueueToRedis(emit=emit, queue=self.queues[queue], redis=self.redis)
        else:
            logger.debug("..preparing formatting..")
            formatted = Format(emit=emit)

        if formatted is None:
            return StatusInfo(210, f"problem during mission formatting", ret[1])

        logger.debug("..formatting..")
        ret = formatted.format()
        if not ret[0]:
            return StatusInfo(211, f"problem during formatting", ret[1])


        # 12. (save formatted positions)
        if self._use_redis:
            logger.debug("..save to Redis..")
            ret = formatted.save()
            if not ret[0]:
                return StatusInfo(212, f"problem during mission save to Redis", ret[1])
        else:
            logger.debug("..saving to file..")
            ret = formatted.saveFile()
            if not ret[0]:
                return StatusInfo(213, f"problem during mission save to file", ret[1])

        # 13. Enqueue positions
        if self._use_redis:
            logger.debug("..enqueue to redis..")
            ret = formatted.enqueue()
            if not ret[0]:
                return StatusInfo(214, f"problem during mission enqueue to Redis", ret[1])
            logger.debug("..saving allocations..")
            self.airport.manager.saveAllocators(self.redis)

        logger.debug("..broadcasting messages..")
        # 14. Create format + format messages
        formatted_message = None
        if self._use_redis:
            formatted_message = EnqueueMessagesToRedis(emit=emit, queue=self.queues["wire"], redis=self.redis)
        else:
            formatted_message = FormatMessage(emit=emit)
        if formatted_message is None:
            return StatusInfo(215, f"problem during formatting of messages", ret[1])
        else:
            ret = formatted_message.format()
            if not ret[0]:
                return StatusInfo(216, f"problem during formatting of messages", ret[1])

        # 15. (save formatted messages)
        if SAVE_TO_FILE:
            logger.debug("..saving messages..")
            ret = formatted_message.saveFile(overwrite=True)
            # Redis: "EnqueueToRedis::save key already exist"
            # File:  "Format::save file already exist"
            if not ret[0] and not ret[1].endswith("already exist"):
                return StatusInfo(217, f"problem during formatted message output save", ret[1])

        # 16. Enqueue messages
        if self._use_redis:
            ret = formatted_message.enqueue()
            if not ret[0]:
                return StatusInfo(218, f"problem during enqueue of messages", ret[1])

        # 17. Done + summary
        logger.debug("..done")
        return StatusInfo(0, "do_mission completed successfully", mission.getId())


    def do_schedule(self, queue, ident, sync, scheduled, do_services: bool = False):

        if not self._use_redis:
            return StatusInfo(300, "do_schedule can currently only schedule movement stored in Redis", None)

        # #########
        # Flight or ground support (service, mission...)
        emit = ReEmit(ident, self.redis)
        emit.setManagedAirport(self)
        emit_time = datetime.fromisoformat(scheduled)
        if emit_time.tzname() is None:  # has no time zone, uses local one
            emit_time = emit_time.replace(tzinfo=self.timezone)
            logger.debug("scheduled time has no time zone, added managed airport local time zone")

        logger.debug("scheduling..")
        ret = emit.schedule(sync, emit_time, do_print=True)
        if not ret[0]:
            return StatusInfo(301, f"problem during rescheduling", ret[1])

        ret = emit.scheduleMessages(sync, emit_time, do_print=True)
        if not ret[0]:
            return StatusInfo(302, f"problem during schedule of messages", ret[1])

        logger.debug("..broadcasting positions..")
        formatted = EnqueueToRedis(emit=emit, queue=self.queues[queue], redis=self.redis)
        ret = formatted.format()
        if not ret[0]:
            return StatusInfo(303, f"problem during rescheduled formatting", ret[1])

        # logger.debug("..saving..")
        # ret = formatted.save(overwrite=True)
        # if not ret[0]:
        #     return StatusInfo(402, f"problem during rescheduled save", ret[1])

        logger.debug("..enqueueing for broadcast..")
        ret = formatted.enqueue()
        if not ret[0]:
            return StatusInfo(304, f"problem during rescheduled enqueing", ret[1])
        logger.debug("..done.")

        logger.debug("..broadcasting messages..")
        formatted_messages = EnqueueMessagesToRedis(emit=emit, queue=self.queues[queue], redis=self.redis)
        ret = formatted_messages.format()
        if not ret[0]:
            return StatusInfo(305, f"problem during rescheduled message formatting", ret[1])

        # logger.debug("..saving..")
        # ret = formatted.save(overwrite=True)
        # if not ret[0]:
        #     return StatusInfo(402, f"problem during rescheduled save", ret[1])

        logger.debug("..enqueueing for broadcast..")
        ret = formatted_messages.enqueue()
        if not ret[0]:
            return StatusInfo(306, f"problem during rescheduled message enqueing", ret[1])

        logger.debug("..saving allocations..")
        self.airport.manager.saveAllocators(self.redis)

        logger.debug("..done.")

        if not (ident.startswith(REDIS_DATABASE.FLIGHTS.value) and ident.endswith(REDIS_TYPE.EMIT.value) and do_services):
            return StatusInfo(0, "scheduled successfully", ident)

        # #########
        # Linked services for flights
        logger.debug(f"scheduling associated services..")
        services = self.airport.manager.allServicesForFlight(redis=self.redis,
                                                            flight_id=ident,
                                                            redis_type=REDIS_TYPE.EMIT.value)

        is_arrival = emit.getMeta("$.move.flight.is_arrival")
        logger.debug(f"..is {'arrival' if is_arrival else 'departure'}..")
        if is_arrival:
            svc_sync = FLIGHT_PHASE.ONBLOCK.value
        else:
            svc_sync = FLIGHT_PHASE.OFFBLOCK.value
        blocktime1 = emit.getAbsoluteEmissionTime(svc_sync)
        blocktime = datetime.fromtimestamp(blocktime1)
        logger.debug(f"..{svc_sync} at {blocktime} ({blocktime1})..done")

        logger.debug(f"..scheduling of services..")
        for service in services:
            logger.debug(f"..doing service {service}..")
            se = ReEmit(service, self.redis)
            se.setManagedAirport(self)
            se_relstart = se.getMeta("$.move.service.ground-support.schedule")
            se_absstart = blocktime + timedelta(minutes=se_relstart)
            logger.debug(f"..service {service} will start at {se_absstart} {se_relstart}min relative to blocktime {blocktime}..")
            self.do_schedule(queue=queue,
                             ident=service,
                             sync=SERVICE_PHASE.START.value,
                             scheduled=se_absstart.isoformat(),
                             do_services=False)
            # we could cut'n paste code from begining of this function as well...
            # I love recursion.

        # not necessary? since completed in last do_schedule
        logger.debug("..saving allocations..")
        self.airport.manager.saveAllocators(self.redis)

        logger.debug(f"..done")
        return StatusInfo(0, "scheduled successfully (with services)", ident)


    def do_emit_again(self, ident, sync, scheduled, new_frequency, queue):

        if not self._use_redis:
            return StatusInfo(400, "do_emit_again can currently only load previous emit from Redis", None)

        emit = ReEmit(ident, self.redis)
        emit.setManagedAirport(self)

        if new_frequency == emit.frequency:
            logger.debug(f"not different")
            return StatusInfo(401, "not a new frequency", ident)

        ret = emit.emit(new_frequency)
        if not ret[0]:
            return StatusInfo(402, f"problem during emit", ret[1])
        # emit.save()

        ret = emit.save(redis=self.redis)
        if not ret[0]:
            return StatusInfo(403, f"problem during save", ret[1])

        emit_time = datetime.fromisoformat(scheduled)
        if emit_time.tzname() is None:  # has no time zone, uses local one
            emit_time = emit_time.replace(tzinfo=self.timezone)
            logger.debug("scheduled time has no time zone, added managed airport local time zone")

        logger.debug("scheduling..")
        ret = emit.schedule(sync, emit_time)
        if not ret[0]:
            return StatusInfo(404, f"problem during rescheduling", ret[1])

        logger.debug("..broadcasting positions..")
        formatted = EnqueueToRedis(emit=emit, queue=self.queues[queue], redis=self.redis)
        ret = formatted.format()
        if not ret[0]:
            return StatusInfo(405, f"problem during rescheduled formatting", ret[1])

        # logger.debug("..saving..")
        # ret = formatted.save(overwrite=True)
        # if not ret[0]:
        #     return StatusInfo(658, f"problem during rescheduled save", ret[1])

        logger.debug("..enqueueing for broadcast..")
        ret = formatted.enqueue()
        if not ret[0]:
            return StatusInfo(406, f"problem during rescheduled enqueing", ret[1])
        logger.debug("..done.")

        logger.debug("..saving allocations..")
        self.airport.manager.saveAllocators(self.redis)

        return StatusInfo(0, "emitted successfully", emit.getKey(REDIS_TYPE.EMIT.value))


    def do_delete(self, queue, ident, do_services:bool = False):
        """ WARNING ** WARNING ** WARNING ** WARNING ** WARNING **
        do_delete is hierarchical. If you delete a key,
        it recursively logically deletes all keys underneath.
        """
        if ident.startswith(REDIS_DATABASE.FLIGHTS.value) and ident.endswith(REDIS_TYPE.EMIT_META.value):
            if do_services:
                services = self.airport.manager.allServicesForFlight(redis=self.redis, flight_id=ident)
                logger.debug(f"deleting services..")
                for service in services:
                    logger.debug(f"..{service}..")
                    si = self.do_delete(queue, service)
                    if si.status != 0:
                        return StatusInfo(501, f"problem during deletion of associated services {service} of {ident} ", si)
                logger.debug(f"..done")

        arr = ident.split(ID_SEP)
        if len(arr) < 2:
            return StatusInfo(502, f"insufficient information to delete entity", ident)

        what = arr[-1]
        logger.debug(f"to delete {ident}, ext={what}")

        if what == REDIS_TYPE.QUEUE.value:
            logger.debug(f"deleting enqueue {ident}..")
            ret = EnqueueToRedis.dequeue(ident=ident, queue=queue, redis=self.redis)  # dequeue and delete
            if not ret[0]:
                return StatusInfo(503, f"problem during deletion of {ident} ", ret)
            self.redis.delete(ident)
            logger.debug(f"{ident} ..done")

        elif what == REDIS_TYPE.EMIT.value:
            logger.debug(f"deleting emit {ident}")
            subkeys = self.redis.keys(key_path(ID_SEP.join(arr[:-1]), "*"))
            for k in subkeys:
                key = k.decode("UTF-8")
                if key != ident:
                    si = self.do_delete(queue=queue, ident=key)
                    if si.status != 0:
                        return StatusInfo(504, f"problem during deletion of associated enqueue {key} of {ident} ", si)
            self.redis.delete(ident)
            logger.debug(f"{ident} ..done")

        elif what == REDIS_TYPE.EMIT_META.value:
            logger.debug(f"deleting META {ident}")
            subkeys = self.redis.keys(key_path(ID_SEP.join(arr[:-1]), "*"))
            for k in subkeys:
                key = k.decode("UTF-8")
                if key != ident:
                    si = self.do_delete(queue=queue, ident=key)
                    if si.status != 0:
                        return StatusInfo(505, f"problem during deletion of associated emit {key} of {ident} ", si)
            self.redis.delete(ident)
            logger.debug(f"{ident} ..done")

        else:
            logger.debug(f"deleting {ident}")
            if arr[0] not in set(item.value for item in REDIS_DATABASE):
                logger.debug(f"no identified database '{arr[0]}' for {ident}")
                return StatusInfo(506, f"no identified database '{arr[0]}' for {ident}", None)
            elif what not in set(item.value for item in REDIS_TYPE):
                logger.debug(f"database '{arr[0]}'")
                logger.debug(f"no identified type '{what}' for {ident}")
                if len(arr) == 2:
                    logger.debug(f"assuming top ident, deleting keys '{ident}:*'")
                    subkeys = self.redis.keys(key_path(ident, "*"))
                    for k in subkeys:
                        self.redis.delete(k)
                        logger.debug(f"deleted {k}")

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
            logger.debug("starttime time has no time zone, added managed airport local time zone")

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
            logger.debug("starttime time has no time zone, added managed airport local time zone")

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


    def do_list(self, mtype = None, rtype = None):  # from, to
        keypattern = "*"
        if mtype is not None:
            keypattern = key_path(mtype, keypattern)
        if rtype is not None:
            keypattern = key_path(keypattern, rtype)
        keys = self.redis.keys(keypattern)
        karr = [(k.decode("UTF-8"), k.decode("UTF-8")) for k in sorted(keys)]
        return karr


    def do_pias_emit(self, queue, ident):
        ret = EnqueueToRedis.pias(redis=self.redis, ident=ident, queue=queue)
        if not ret[0]:
            return StatusInfo(900, f"problem during pias of {ident}", ret)
        return StatusInfo(0, "pias successfully", None)


    def list_syncmarks(self, ident):
        emit = ReEmit(ident, self.redis)
        return list(emit.getMarkList())

    def list_messages(self, ident):
        emit = ReEmit(ident, self.redis)
        return list(emit.getMarkList())
