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
from emitpy.service import Service, ServiceMove, FlightServices, Mission, MissionMove
from emitpy.emit import Emit, ReEmit
from emitpy.broadcast import Format, EnqueueToRedis, FormatMessage, EnqueueMessagesToRedis, Queue
# pylint: disable=W0611
from emitpy.constants import SERVICE_PHASE, MISSION_PHASE, FLIGHT_PHASE, FEATPROP, ARRIVAL, LIVETRAFFIC_QUEUE, LIVETRAFFIC_FORMATTER
from emitpy.constants import INTERNAL_QUEUES, ID_SEP, REDIS_TYPE, REDIS_DB, key_path, REDIS_DATABASE, REDIS_PREFIX
from emitpy.constants import MANAGED_AIRPORT_KEY, MANAGED_AIRPORT_LAST_UPDATED, AIRAC_CYCLE
from emitpy.parameters import REDIS_CONNECT, REDIS_ATTEMPTS, REDIS_WAIT, XPLANE_FEED
from emitpy.airport import Airport, AirportWithProcedures, XPAirport
from emitpy.airspace import XPAerospace
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


    def do_flight(self, queue, emit_rate, airline, flightnumber, scheduled, apt, movetype, actype, ramp, icao24, acreg, runway: str = None, load_factor:float = 1.0, is_cargo: bool = False, do_services: bool = False, actual_datetime: str = None):
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

        logger.debug("airline, airport..")
        # Add pure commercial stuff
        airline = Airline.find(airline, self.redis)
        if airline is None:
            logger.error("airline not found")
            return StatusInfo(1, "error", None)

        remote_apt = Airport.find(apt, self.redis)
        if remote_apt is None:
            logger.error("remote airport not found")
            return StatusInfo(100, "error", None)

        aptrange = self.airport.miles(remote_apt)
        logger.debug("..done")

        logger.debug("remote airport..")
        remote_apt = AirportWithProcedures.new(remote_apt)  # @todo: ManagedAirportBase
        logger.debug(f"remote airport is {remote_apt}")

        # if self._use_redis:
        #     prevdb = self.redis.client_info()["db"]
        #     self._app.redis.select(1)
        #     remote_apt.save("airports", self.use_redis())
        #     self._app.redis.select(prevdb)
        #     logger.debug(f"remote airport saved")

        scheduled_dt = datetime.fromisoformat(scheduled)
        if scheduled_dt.tzname() is None:  # has no time zone, uses local one
            scheduled_dt = scheduled_dt.replace(tzinfo=self.timezone)
            logger.debug("scheduled time has no time zone, added managed airport local time zone")

        logger.debug("..collecting metar for remote airport..")
        dt2 = datetime.now().astimezone(self.timezone) - timedelta(days=1)
        if scheduled_dt < dt2:
            remote_apt.update_metar(moment=scheduled_dt, redis=self.redis) 
        else:
            remote_apt.update_metar(redis=self.redis) 
        logger.debug("..done")

        logger.debug("loading aircraft..")
        acarr = (actype, actype) if type(actype) == str else actype
        actype, acsubtype = acarr
        ac = AircraftTypeWithPerformance.findAircraftByType(actype, acsubtype, self.use_redis())
        if ac is None:
            return StatusInfo(105, f"aircraft performance not found for {actype} or {acsubtype}", None)
        acperf = AircraftTypeWithPerformance.find(icao=ac, redis=self.use_redis())
        if acperf is None:
            return StatusInfo(110, f"aircraft performance not found for {ac}", None)
        acperf.load()
        reqfl = acperf.FLFor(aptrange)
        aircraft = Aircraft(registration=acreg, icao24= icao24, actype=acperf, operator=airline)
        aircraft.save(self.redis)
        logger.debug("..done")

        # logger.info("*" * 90)
        logger.info("***** (%s, %dnm) %s-%s AC %s at FL%d" % (
                    remote_apt.getProp(FEATPROP.CITY.value), aptrange/NAUTICAL_MILE, remote_apt.iata, self.iata,
                    acperf.typeId, reqfl))
        # logger.debug("*" * 89)

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
        else:
            flight = Departure(operator=airline,
                               number=flightnumber,
                               scheduled=scheduled_dt,
                               managedAirport=self,
                               destination=remote_apt,
                               aircraft=aircraft,
                               load_factor=load_factor)
        if is_cargo:
            flight.set_cargo()
        if runway is not None and runway != "":
            self.airport.setRunwaysInUse(runway)
        flight.setFL(reqfl)
        rampval = self.airport.getRamp(ramp, redis=self.use_redis())
        if rampval is None:
            logger.warning(f"ramp {ramp} not found, quitting")
            return StatusInfo(115, f"ramp {ramp} not found", None)

        flight.setRamp(rampval)
        gate = "C99"
        ramp_name = rampval.getName()
        if ramp_name[0] in "A,B,C,D,E".split(",") and len(ramp) < 5:  # does now work for "Cargo Ramp F5" ;-)
            gate = ramp_name
        flight.setGate(gate)

        aircraft.setCallsign(airline.icao+flightnumber)

        logger.debug("..planning..")
        ret = flight.plan()
        if not ret[0]:
            return StatusInfo(120, f"problem during flight planning", ret[1])

        logger.debug(f"route: {flight.printFlightRoute()}")
        logger.debug(f"plan : {flight.printFlightPlan()}")

        logger.debug("..flying..")
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
            return StatusInfo(125, f"problem during move", ret[1])
        # move.save()

        logger.debug("..emission positions..")
        emit = Emit(move)
        ret = emit.emit(emit_rate)
        if not ret[0]:
            return StatusInfo(130, f"problem during emit", ret[1])
        # emit.save()

        logger.debug("..scheduling..")
        # Schedule actual time if supplied
        logger.debug(f"scheduled={scheduled}, actual={actual_datetime} ({sync})")
        emit_time_str = actual_datetime if actual_datetime is not None else scheduled
        emit_time = datetime.fromisoformat(emit_time_str)
        if emit_time.tzname() is None:  # has no time zone, uses local one
            emit_time = emit_time.replace(tzinfo=self.timezone)
            logger.debug("scheduled time has no time zone, added managed airport local time zone")

        ret = emit.schedule(sync, emit_time, do_print=True)
        if not ret[0]:
            return StatusInfo(135, f"problem during schedule", ret[1])

        ret = emit.scheduleMessages(sync, emit_time, do_print=True)
        if not ret[0]:
            return StatusInfo(140, f"problem during schedule of messages", ret[1])

        logger.debug("..saving..")
        if SAVE_TO_FILE or SAVE_TRAFFIC:
            ret = emit.saveFile()
            if not ret[0]:
                return StatusInfo(145, f"problem during save to file", ret[1])

        ret = emit.save(redis=self.redis)
        if not ret[0]:
            return StatusInfo(150, f"problem during save", ret[1])

        logger.debug("..broadcasting positions..")
        formatted = None
        if self._use_redis:
            formatted = EnqueueToRedis(emit=emit, queue=self.queues[queue], redis=self.redis)
        else:
            formatted = Format(emit=emit)
        if formatted is None:
            return StatusInfo(155, f"problem during formatting", ret[1])
        else:
            ret = formatted.format()
            if not ret[0]:
                return StatusInfo(160, f"problem during formatting", ret[1])

        if SAVE_TO_FILE:
            logger.debug("..saving..")
            ret = formatted.saveFile()
            # Redis: "EnqueueToRedis::save key already exist"
            # File:  "Format::save file already exist"
            if not ret[0] and not ret[1].endswith("already exist"):
                return StatusInfo(165, f"problem during formatted output save", ret[1])

        logger.debug("..sending messages..")
        formatted_message = None
        if self._use_redis:
            formatted_message = EnqueueMessagesToRedis(emit=emit, queue=self.queues["wire"], redis=self.redis)
        else:
            formatted_message = FormatMessage(emit=emit)
        if formatted_message is None:
            return StatusInfo(170, f"problem during formatting of messages", ret[1])
        else:
            ret = formatted_message.format()
            if not ret[0]:
                return StatusInfo(175, f"problem during formatting of messages", ret[1])

        if SAVE_TO_FILE:
            logger.debug("..saving messages..")
            ret = formatted_message.saveFile(overwrite=True)
            # Redis: "EnqueueToRedis::save key already exist"
            # File:  "Format::save file already exist"
            if not ret[0] and not ret[1].endswith("already exist"):
                return StatusInfo(180, f"problem during formatted output save", ret[1])

        if self._use_redis:
            ret = formatted_message.enqueue()
            if not ret[0]:
                return StatusInfo(185, f"problem during enqueue of messages", ret[1])

        logger.info("SAVED " + ("*" * 92))
        if not do_services:
            logger.debug("..done")
            return StatusInfo(0, "completed successfully", flight.getId())

        logger.debug("*" * 110)
        logger.debug(f"**** {airline.iata}{flightnumber} {scheduled} {movetype} {fromto} {apt} {actype} {icao24} {acreg} {ramp} {runway}")
        logger.debug(f"* done schedule {FLIGHT_PHASE.TOUCH_DOWN.value if movetype == ARRIVAL else FLIGHT_PHASE.TAKE_OFF.value} {actual_datetime if actual_datetime is not None else scheduled}")

        logger.debug("..servicing..")
        st = emit.getRelativeEmissionTime(sync)
        bt = emit.getRelativeEmissionTime(svc_sync)  # 0 for departure...
        td = bt - st
        blocktime = emit_time + timedelta(seconds=td)

        logger.info(f"**** {airline.iata}{flightnumber} Services scheduled {FLIGHT_PHASE.ONBLOCK.value if movetype == ARRIVAL else FLIGHT_PHASE.OFFBLOCK.value} {blocktime}")
        logger.debug("*" * 109)

        # @todo: pass service operator
        operator = Company(orgId="Airport Operator", classId="Airport Operator", typeId="Airport Operator", name=self.operator)
        # operator = self.airport.manager.getCompany(operator)

        flight_service = FlightServices(flight, operator)
        flight_service.setManagedAirport(self)
        ret = flight_service.service()
        if not ret[0]:
            return StatusInfo(200, f"problem during flight service", ret[1])

        logger.debug("..moving equipment..")
        ret = flight_service.move()
        if not ret[0]:
            return StatusInfo(205, f"problem during flight service movement creation", ret[1])

        logger.debug("..emission positions equipment..")
        ret = flight_service.emit(emit_rate_svc)
        if not ret[0]:
            return StatusInfo(210, f"problem during flight service emission", ret[1])

        logger.debug("..scheduling equipment..")
        ret = flight_service.schedule(blocktime, do_print=True)
        if not ret[0]:
            return StatusInfo(220, f"problem during flight service scheduling", ret[1])

        logger.debug("..scheduling messages..")
        ret = flight_service.scheduleMessages(blocktime, do_print=True)
        if not ret[0]:
            return StatusInfo(225, f"problem during flight service scheduling of messages", ret[1])

        logger.debug("..saving equipment and messages..")
        if SAVE_TO_FILE or SAVE_TRAFFIC:
            ret = flight_service.saveFile()
            if not ret[0]:
                return StatusInfo(230, f"problem during flight service scheduling", ret[1])
        ret = flight_service.save(redis=self.redis)
        if not ret[0]:
            return StatusInfo(235, f"problem during flight service save in Redis", ret[1])

        logger.debug("..broadcasting positions..")
        if self._use_redis:
            ret = flight_service.enqueueToRedis(self.queues[queue])  # also enqueues...
            if not ret[0]:
                return StatusInfo(240, f"problem during enqueue of services", ret[1])

        logger.debug("..broadcasting messages..")
        if self._use_redis:
            ret = flight_service.enqueueMessagesToRedis(self.queues["wire"])  # also enqueues...
            if not ret[0]:
                return StatusInfo(245, f"problem during enqueue of services", ret[1])

            self.airport.manager.saveAllocators(self.redis)
        else:
            ret = flight_service.format(saveToFile=True)
            if not ret[0] and not ret[1].endswith("already exist"):
                return StatusInfo(250, f"problem during formating", ret[1])


        logger.info("SERVICED " + ("*" * 89))
        logger.debug("..done, service included.")
        return StatusInfo(0, "completed successfully", flight.getId())


    def do_service(self, queue, emit_rate, operator, service, quantity, ramp, aircraft, equipment_ident, equipment_icao24, equipment_model, equipment_startpos, equipment_endpos, scheduled):
        logger.debug("loading aircraft..")
        acperf = AircraftTypeWithPerformance.find(aircraft, redis=self.use_redis())
        if acperf is None:
            return StatusInfo(300, f"EmitApp:do_service: aircraft performance {aircraft} not found", None)
        acperf.load()
        logger.debug(f"..done {acperf.available}")

        operator = Company(orgId="Airport Operator", classId="Airport Operator", typeId="Airport Operator", name=self.operator)

        logger.debug("creating service..")
        rampval = self.airport.getRamp(ramp, redis=self.use_redis())
        if rampval is None:
            return StatusInfo(305, f"EmitApp:do_service: ramp {ramp} not found", None)
        scheduled_dt = datetime.fromisoformat(scheduled)
        if scheduled_dt.tzname() is None:  # has no time zone, uses local one
            scheduled_dt = scheduled_dt.replace(tzinfo=self.timezone)
            logger.debug("scheduled time has no time zone, added managed airport local time zone")
        this_service = Service.getService(service)(scheduled=scheduled_dt,
                                                   ramp=rampval,
                                                   operator=operator,
                                                   quantity=quantity)
        this_service.setAircraftType(acperf)
        this_equipment = self.airport.manager.selectEquipment(operator=operator, service=this_service, reqtime=scheduled_dt, model=equipment_model, registration=equipment_ident, use=True)
        if this_equipment is None:
            return StatusInfo(310, f"EmitApp:do_service: vehicle not found", None)
        this_equipment.setICAO24(equipment_icao24)
        startpos = self.airport.selectServicePOI(equipment_startpos, service, redis=self.use_redis())
        if startpos is None:
            return StatusInfo(315, f"EmitApp:do_service: start position {equipment_startpos} for {service} not found", None)
        this_equipment.setPosition(startpos)  # this is the start position for the vehicle
        nextpos = self.airport.selectServicePOI(equipment_endpos, service, redis=self.use_redis())
        if nextpos is None:
            return StatusInfo(325, f"EmitApp:do_service: start position {equipment_endpos} for {service} not found", None)
        this_equipment.setNextPosition(nextpos)  # this is the position the vehicle is going to after service

        logger.debug("..moving..")
        move = ServiceMove(this_service, self.airport)
        ret = move.move()
        if not ret[0]:
            return StatusInfo(330, f"problem during service move", ret[1])
        if SAVE_TO_FILE:
            ret = move.saveFile()
            if not ret[0]:
                return StatusInfo(335, f"problem during service move save", ret[1])
        logger.debug("..emission positions..")
        emit = Emit(move)
        ret = emit.emit(emit_rate)
        if not ret[0]:
            return StatusInfo(340, f"problem during service emission", ret[1])

        service_duration = this_service.duration()

        logger.debug(f"..service duration {service_duration}..")
        emit.addToPause(SERVICE_PHASE.SERVICE_START.value, service_duration)
        # will trigger new call to emit.emit(emit_rate) to adjust

        logger.debug("..scheduling broadcast..")
        # default is to serve at scheduled time
        logger.debug(f"..{SERVICE_PHASE.SERVICE_START.value} at {scheduled}..")
        ret = emit.schedule(SERVICE_PHASE.SERVICE_START.value, scheduled_dt)
        if not ret[0]:
            return StatusInfo(345, f"problem during service scheduling", ret[1])
        if SAVE_TO_FILE:
            ret = emit.saveFile()
            if not ret[0]:
                return StatusInfo(350, f"problem during service emission save", ret[1])
        ret = emit.save(redis=self.redis)
        if not ret[0]:
            return StatusInfo(355, f"problem during service emission save to Redis", ret[1])

        logger.debug("..broadcasting position..")
        formatted = None
        if self._use_redis:
            logger.debug("..enqueue to redis..")
            formatted = EnqueueToRedis(emit=emit, queue=self.queues[queue], redis=self.redis)
            if formatted is None:
                return StatusInfo(360, f"problem during service formatting", ret[1])
            else:
                logger.debug("..save to Redis..")
                ret = formatted.save()
                if not ret[0]:
                    return StatusInfo(365, f"problem during service save to Redis", ret[1])
                logger.debug("..enqueue to redis..")
                ret = formatted.enqueue()
                if not ret[0]:
                    return StatusInfo(370, f"problem during service enqueue to Redis", ret[1])
        else:
            formatted = Format(emit=emit)
            if formatted is None:
                return StatusInfo(375, f"problem during service formatting", ret[1])
            else:
                logger.debug("..formatting..")
                ret = formatted.format()
                if not ret[0]:
                    return StatusInfo(380, f"problem during formatting", ret[1])
                else:
                    logger.debug("..saving..")
                    ret = formatted.saveFile()
                    if not ret[0]:
                        return StatusInfo(385, f"problem during service save to file", ret[1])

        logger.debug("..done")

        return StatusInfo(0, "completed successfully", this_service.getId())


    def do_flight_services(self, emit_rate, queue, operator, flight_id, estimated = None):
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
        # we "just need" actype and ramp
        logger.debug(f"got flight: {flight.getInfo()}")

        flight_service = FlightServices(flight, operator)
        flight_service.setManagedAirport(self)
        ret = flight_service.service()
        if not ret[0]:
            return StatusInfo(410, f"problem during flight service", ret[1])

        logger.debug("..moving equipment..")
        ret = flight_service.move()
        if not ret[0]:
            return StatusInfo(415, f"problem during flight service movement creation", ret[1])

        logger.debug("..emiting positions equipment..")
        ret = flight_service.emit(emit_rate)
        if not ret[0]:
            return StatusInfo(420, f"problem during flight service emission", ret[1])

        logger.debug("..scheduling equipment..")
        ret = flight_service.schedule(blocktime)
        if not ret[0]:
            return StatusInfo(425, f"problem during flight service scheduling", ret[1])

        logger.debug("..saving equipment..")
        if SAVE_TO_FILE:
            ret = flight_service.saveFile()
            if not ret[0]:
                return StatusInfo(430, f"problem during flight service scheduling", ret[1])
        ret = flight_service.save(redis=self.redis)
        if not ret[0]:
            return StatusInfo(435, f"problem during flight service save in Redis", ret[1])

        logger.debug("..broadcasting positions..")
        ret = flight_service.enqueueToRedis(self.queues[queue])
        if not ret[0]:
            return StatusInfo(440, f"problem during enqueue of services", ret[1])

        self.airport.manager.saveAllocators(self.redis)

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
        logger.debug("creating mission..")
        if len(checkpoints) == 0:
            k = 3
            checkpoints = [c[0] for c in random.choices(self.airport.getCheckpointCombo(), k=k)]  # or getPOICombo()
            logger.debug(f"..no checkpoint, generating {k} random checkpoint ({checkpoints})..")

        operator = self.airport.manager.getCompany(operator)
        mission = Mission(operator=operator, checkpoints=checkpoints, name=mission)

        mission_time = datetime.fromisoformat(scheduled)
        if mission_time.tzname() is None:  # has no time zone, uses local one
            mission_time = mission_time.replace(tzinfo=self.timezone)
            logger.debug("scheduled time has no time zone, added managed airport local time zone")

        logger.debug("..vehicle..")
        mission_equipment = self.airport.manager.selectEquipment(operator=operator, service=mission, reqtime=mission_time, model=equipment_model, registration=equipment_ident, use=True)
        if mission_equipment is None:
            return StatusInfo(311, f"connot find vehicle {equipment_model}", None)
        mission_equipment.setICAO24(equipment_icao24)

        logger.debug("..start and end positions..")
        start_pos = self.airport.getPOIFromCombo(equipment_startpos)
        if start_pos is None:
            return StatusInfo(300, f"connot find start position {equipment_startpos}", None)
        mission_equipment.setPosition(start_pos)
        end_pos = self.airport.getPOIFromCombo(equipment_endpos)
        if end_pos is None:
            return StatusInfo(301, f"connot find end position {equipment_endpos}", None)
        mission_equipment.setNextPosition(end_pos)

        # logger.debug("..running..")
        # mission.run()  # do nothing...

        logger.debug("..moving..")
        move = MissionMove(mission, self.airport)
        ret = move.move()
        if not ret[0]:
            return StatusInfo(302, f"problem during mission move", ret[1])
        if SAVE_TO_FILE:
            ret = move.saveFile()
            if not ret[0]:
                return StatusInfo(303, f"problem during mission move save", ret[1])

        logger.debug("..emiting positions..")
        emit = Emit(move)
        ret = emit.emit(emit_rate)
        if not ret[0]:
            return StatusInfo(304, f"problem during mission emission", ret[1])

        logger.debug("..scheduling broadcast..")
        ret = emit.schedule(MISSION_PHASE.START.value, mission_time)
        if not ret[0]:
            return StatusInfo(305, f"problem during mission scheduling", ret[1])
        if SAVE_TO_FILE or SAVE_TRAFFIC:
            ret = emit.saveFile()
            if not ret[0]:
                return StatusInfo(306, f"problem during mission emission save", ret[1])
        logger.debug("..saving..")
        ret = emit.save(redis=self.redis)
        if not ret[0]:
            return StatusInfo(307, f"problem during service mission save to Redis", ret[1])


        logger.debug("..broadcasting position..")
        formatted = None
        if self._use_redis:
            logger.debug("..enqueue to redis..")
            formatted = EnqueueToRedis(emit=emit, queue=self.queues[queue], redis=self.redis)
            if formatted is None:
                return StatusInfo(310, f"problem during service formatting", ret[1])
            else:
                logger.debug("..save to Redis..")
                ret = formatted.save()
                if not ret[0]:
                    return StatusInfo(311, f"problem during service save to Redis", ret[1])
                logger.debug("..enqueue to redis..")
                ret = formatted.enqueue()
                if not ret[0]:
                    return StatusInfo(312, f"problem during service enqueue to Redis", ret[1])

            self.airport.manager.saveAllocators(self.redis)
        else:
            formatted = Format(emit=emit)
            if formatted is None:
                return StatusInfo(313, f"problem during service formatting", ret[1])
            else:
                logger.debug("..formatting..")
                ret = formatted.format()
                if not ret[0]:
                    return StatusInfo(314, f"problem during formatting", ret[1])
                else:
                    logger.debug("..saving..")
                    ret = formatted.saveFile()
                    if not ret[0]:
                        return StatusInfo(315, f"problem during service save to file", ret[1])

        logger.debug("..done")
        return StatusInfo(0, "do_mission completed successfully", mission.getId())


    def do_schedule(self, queue, ident, sync, scheduled, do_services: bool = False):

        if not self._use_redis:
            return StatusInfo(399, "do_schedule can currently only schedule movement stored in Redis", None)

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
            return StatusInfo(400, f"problem during rescheduling", ret[1])

        ret = emit.scheduleMessages(sync, emit_time, do_print=True)
        if not ret[0]:
            return StatusInfo(105, f"problem during schedule of messages", ret[1])

        logger.debug("..broadcasting positions..")
        formatted = EnqueueToRedis(emit=emit, queue=self.queues[queue], redis=self.redis)
        ret = formatted.format()
        if not ret[0]:
            return StatusInfo(401, f"problem during rescheduled formatting", ret[1])

        # logger.debug("..saving..")
        # ret = formatted.save(overwrite=True)
        # if not ret[0]:
        #     return StatusInfo(402, f"problem during rescheduled save", ret[1])

        logger.debug("..enqueueing for broadcast..")
        ret = formatted.enqueue()
        if not ret[0]:
            return StatusInfo(403, f"problem during rescheduled enqueing", ret[1])
        logger.debug("..done.")

        self.airport.manager.saveAllocators(self.redis)
        if not do_services:
            return StatusInfo(0, "scheduled successfully", ident)

        if ident.startswith(REDIS_DATABASE.FLIGHTS.value) and ident.endswith(REDIS_TYPE.EMIT.value) and do_services:
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

            logger.debug(f"scheduling..")
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

            self.airport.manager.saveAllocators(self.redis)
            logger.debug(f"..done")

        return StatusInfo(0, "scheduled successfully (with services)", ident)


    def do_emit_again(self, ident, sync, scheduled, new_frequency, queue):

        if not self._use_redis:
            return StatusInfo(659, "do_emit_again can currently only load previous emit from Redis", None)

        emit = ReEmit(ident, self.redis)
        emit.setManagedAirport(self)

        if new_frequency == emit.frequency:
            logger.debug(f"not different")
            return StatusInfo(651, "not a new frequency", ident)

        ret = emit.emit(new_frequency)
        if not ret[0]:
            return StatusInfo(654, f"problem during emit", ret[1])
        # emit.save()

        ret = emit.save(redis=self.redis)
        if not ret[0]:
            return StatusInfo(655, f"problem during save", ret[1])

        emit_time = datetime.fromisoformat(scheduled)
        if emit_time.tzname() is None:  # has no time zone, uses local one
            emit_time = emit_time.replace(tzinfo=self.timezone)
            logger.debug("scheduled time has no time zone, added managed airport local time zone")

        logger.debug("scheduling..")
        ret = emit.schedule(sync, emit_time)
        if not ret[0]:
            return StatusInfo(656, f"problem during rescheduling", ret[1])

        logger.debug("..broadcasting positions..")
        formatted = EnqueueToRedis(emit=emit, queue=self.queues[queue], redis=self.redis)
        ret = formatted.format()
        if not ret[0]:
            return StatusInfo(657, f"problem during rescheduled formatting", ret[1])

        # logger.debug("..saving..")
        # ret = formatted.save(overwrite=True)
        # if not ret[0]:
        #     return StatusInfo(658, f"problem during rescheduled save", ret[1])

        logger.debug("..enqueueing for broadcast..")
        ret = formatted.enqueue()
        if not ret[0]:
            return StatusInfo(659, f"problem during rescheduled enqueing", ret[1])
        logger.debug("..done.")

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
                return StatusInfo(502, f"problem during deletion of {ident} ", ret)
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
                        return StatusInfo(503, f"problem during deletion of associated enqueue {key} of {ident} ", si)
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
                        return StatusInfo(504, f"problem during deletion of associated emit {key} of {ident} ", si)
            self.redis.delete(ident)
            logger.debug(f"{ident} ..done")

        else:
            logger.debug(f"deleting {ident}")
            if arr[0] not in set(item.value for item in REDIS_DATABASE):
                logger.debug(f"no identified database '{arr[0]}' for {ident}")
                return StatusInfo(570, f"no identified database '{arr[0]}' for {ident}", None)
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
            return StatusInfo(500, f"problem during pias of {ident}", ret)
        return StatusInfo(0, "pias successfully", None)


    def list_syncmarks(self, ident):
        emit = ReEmit(ident, self.redis)
        return list(emit.getMarkList())

