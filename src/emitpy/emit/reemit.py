#
import logging
import json
from datetime import datetime, timedelta
from jsonpath import JSONPath

from .emit import EmitPoint, Emit
# pylint: disable=C0411
from emitpy.message import EstimatedTimeMessage
from emitpy.constants import ID_SEP, FEATPROP, MOVE_TYPE, FLIGHT_PHASE, SERVICE_PHASE, MISSION_PHASE
from emitpy.constants import REDIS_DATABASES, REDIS_TYPE, FLIGHT_DATABASE
from emitpy.parameters import MANAGED_AIRPORT_AODB
from emitpy.utils import Timezone


logger = logging.getLogger("ReEmit")


class ReEmit(Emit):
    """
    Loads previsously saved Emit output and compute new emission points
    based on new schedule or added pauses.
    """
    def __init__(self, ident: str, redis):
        """
        Creates a Emit instance from cached data.
        This instance will not have any reference to a move instance.
        We keep minimal move information in «emit meta».

        ident should be the emit key used to store emit points.
        """
        Emit.__init__(self, move=None)
        self.redis = redis # this is a local sign we use Redis
        self.managedAirport = None

        ret = self.parseKey(ident)
        if ret[0]:
            ret1 = self.load()
            if not ret1[0]:
                logger.warning(f":init: could not load {ident}")
        else:
            logger.warning(f":init: could not parse {ident}")

        if self.moves is None:
            logger.warning(f":__init__: {ident} not loaded")


    def setManagedAirport(self, airport):
        self.managedAirport = airport


    def parseKey(self, key: str):
        """
        Figure out what's being loaded (type of move)
        from key root part which should be a well-known database.
        Extract frequency from key to allow for same move with several emission frequency.

        :param      emit_key:    The emit identifier
        :type       emit_key:    str
        :param      extension:  The extension
        :type       extension:  str
        """
        valid_extensions = set(item.value for item in REDIS_TYPE)
        valid_databases = dict([(v, k) for k, v in REDIS_DATABASES.items()])

        arr = key.split(ID_SEP)

        # Do we have an extension?
        if arr[-1] != REDIS_TYPE.EMIT.value:
            logger.warning(f":parseKey: invalid emit key {key} (extension={arr[-1]})")
            return (False, "ReEmit::parseKey invalid emit key")

        if arr[0] not in valid_databases.keys():
            logger.warning(f":parseKey: invalid emit key {key} (database={arr[0]})")
            return (False, "ReEmit::parseKey invalid emit key")

        self.emit_type = valid_databases[arr[0]]
        self.frequency = int(arr[-2])
        self.emit_id = ID_SEP.join(arr[1:-2])

        logger.debug(f":parseKey: {arr}: emit_type={self.emit_type}, emit_id={self.emit_id}, frequency={self.frequency}")
        return (True, "ReEmit::parseKey parsed")


    def load(self):
        # First load meta in case we need some info
        status = self.loadMetaFromCache()
        if not status[0]:
            return status

        status = self.loadFromCache()
        if not status[0]:
            return status

        status = self.extractMove()
        if not status[0]:
            return status

        return (True, "ReEmit::load loaded")


    def loadMetaFromCache(self):
        meta_id = self.getKey(REDIS_TYPE.EMIT_META.value)
        logger.debug(f":loadMetaFromCache: trying to read {meta_id}..")
        if self.redis.exists(meta_id):
            self.emit_meta = self.redis.json().get(meta_id)
            logger.debug(f":loadMetaFromCache: ..got {len(self.emit_meta)} meta data")
            # logger.debug(f":loadMetaFromCache: {self.emit_meta}")
        else:
            logger.debug(f":loadMetaFromCache: ..no meta for {meta_id}")
        return (True, "ReEmit::loadMetaFromCache loaded")


    def loadFromCache(self):
        def toEmitPoint(s: str):
            f = json.loads(s.decode('UTF-8'))
            return EmitPoint.new(f)

        emit_id = self.getKey(REDIS_TYPE.EMIT.value)
        logger.debug(f":loadFromCache: trying to read {emit_id}..")
        ret = self.redis.zrange(emit_id, 0, -1)
        if ret is not None:
            logger.debug(f":loadFromCache: ..got {len(ret)} members")
            self._emit = [toEmitPoint(f) for f in ret]
            logger.debug(f":loadFromCache: ..collected {len(self._emit)} points")
        else:
            logger.debug(f":loadFromCache: ..could not load {emit_id}")
        return (True, "ReEmit::loadFromCache loaded")


    def getMeta(self, path: str = None, return_first_only: bool = True):
        # logger.debug(f":getMeta: from ReEmit")
        if self.emit_meta is None:
            ret = self.loadMetaFromCache()
            if not ret[0]:
                logger.warning(f":getMeta: load meta returned error {ret[1]}")
                return None
        if path is not None:
            arr = JSONPath(path).parse(self.emit_meta)
            if arr is not None and len(arr) > 0:
                return arr if not return_first_only else arr[0]
            return None  # arr is either None or len(arr)==0
        # return entire meta structure
        return self.emit_meta


    def loadFromFile(self, emit_id):
        # load output of Movement file.
        basename = os.path.join(MANAGED_AIRPORT_AODB, FLIGHT_DATABASE, emit_id)

        filename = os.path.join(basename, "-4-move.json")
        if os.path.exists(filename):
            with open(filename, "r") as fp:
                self.moves = json.load(fp)
            self.emit_id = emit_id
            logger.debug(":loadAll: loaded %d " % self.emit_id)
            return (True, "Movement::load loaded")

        logger.debug(f":loadAll: cannot find {filename}")
        return (False, "ReEmit::loadFromFile not loaded")


    def extractMove(self):
        """
        Move points are saved in emission points.
        """
        self.moves = list(filter(lambda f: not f.getProp(FEATPROP.BROADCAST.value), self._emit))
        logger.debug(f":extractMove: extracted {len(self.moves)} points")
        return (True, "ReEmit::extractMove loaded")


    # def parseMeta(self):
    #     """
    #     Reinstall meta data in Emit object based on its type (flight, service, mission).
    #     Each meta data is carefully extracted from a JSON path.
    #     """
    #     def getData(path: str):
    #         val = JSONPath(path).parse(self.emit_meta)
    #         if val is None:
    #             logger.warning(f":parseMeta: no value for {path}")
    #         return val

    #     if self.emit_type == "flight":
    #         pass
    #     elif self.emit_type == "service":
    #         pass
    #     elif self.emit_type == "misssion":
    #         pass
    #     else:
    #         logger.warning(f":parseMeta: invalid type {self.emit_type}")

    #     return (True, "ReEmit::parseMeta loaded")



    # For the following functions, recall we don't have a self.move, just self.moves (the points).
    # All we have are meta data associated with the move, that was saved at that time.
    # So the following functions mainly aims at adjusting the meta data associated with the move
    # to add the new estimate.
    # A function also copies the new estimatated time to resources used.
    def getEstimatedTime(self):
        """
        Gets the time of the start of the source move for departure/mission/service
        or the end of the source move for arrival
        """
        if self.managedAirport is None:
            logger.warning(f":getEstimatedTime: managedAirport not set")
            return None

        mark = None
        if self.emit_type == MOVE_TYPE.FLIGHT.value:
            is_arrival = self.getMeta("$.move.is_arrival")
            if is_arrival is None:
                logger.warning(f":getEstimatedTime: cannot get move for {self.emit_id}")
            mark = FLIGHT_PHASE.TOUCH_DOWN.value if is_arrival else FLIGHT_PHASE.TAKE_OFF.value
        elif self.emit_type == MOVE_TYPE.SERVICE.value:
            mark = SERVICE_PHASE.SERVICE_START.value
        elif self.emit_type == MOVE_TYPE.MISSION.value:
            mark = MISSION_PHASE.START.value

        if mark is not None:
            f = self.getAbsoluteEmissionTime(mark)
            if f is not None:
                return datetime.fromtimestamp(f, tz=self.managedAirport.timezone)
            else:
                logger.warning(f":getEstimatedTime: no feature at mark {mark}")
        else:
            logger.warning(f":getEstimatedTime: no mark")

        logger.warning(f":getEstimatedTime: could not estimate")
        return None


    def updateEstimatedTime(self):
        """
        Copies the estimated time into movement meta data.
        """
        et = self.getEstimatedTime()
        ident = self.emit_id
        if et is not None:
            etinfo = self.getMeta("$.time")
            estat = datetime.now().astimezone()
            if etinfo is not None:
                    etinfo.append( (et.isoformat(), "ET", estat.isoformat()) )
            else:
                logger.debug(f":updateEstimatedTime: {ident} had no estimates, adding")
                if self.emit_meta is not None:
                    self.emit_meta["time"] = [et.isoformat(), "ET", estat.isoformat()]
            logger.debug(f":updateEstimatedTime: {ident} added ET {et}")

            if self.emit_meta is not None:
                self.saveMeta(self.redis)
            else:
                logger.warning(f":updateEstimatedTime: {ident} had no meta data")

            self.updateResources(et)
            return (True, "ReEmit::updateEstimatedTime updated")

        logger.warning(f":updateEstimatedTime: no estimated time")
        return (True, "ReEmit::updateEstimatedTime updated")


    def updateResources(self, et: datetime):
        """
        Complicated for now. We need to update the in-memory structure.
        1. Make sure it is loaded (especially if redis, what if not found??)
        2. Update it
        3. If redis: save it.

        :param      et:          { parameter_description }
        :type       et:          datetime
        :param      is_arrival:  Indicates if arrival
        :type       is_arrival:  bool
        """
        if self.managedAirport is None:
            logger.warning(f":updateResources: managedAirport not set")
            return (False, "ReEmit::updateResources: managedAirport not set")

        # 1. What is the underlying move?
        if self.emit_type == MOVE_TYPE.FLIGHT.value:
            # 2. What is the resource identifier
            fid = self.getMeta("$.props.flight.identifier")
            is_arrival = self.getMeta("$.move.is_arrival")
            if fid is not None:
                am = self.managedAirport.airport.manager

                TIME_NEW_ET_ADVANCE_WARNING=-1800
                self.addMessage(EstimatedTimeMessage(flight_id=fid,
                                                 is_arrival=is_arrival,
                                                 scheduled_time=et,
                                                 relative_time=TIME_NEW_ET_ADVANCE_WARNING,
                                                 et=et))
                logger.debug(f":updateResources: sent new estimate message {fid}: {et}")

                # 3. For flight: update runway, ramp
                rwy = self.getMeta("$.props.flight.runway.resource")
                et_from = et - timedelta(minutes=3)
                et_to   = et + timedelta(minutes=3)
                rwrsc = am.runway_allocator.findReservation(rwy, fid, self.redis)
                if rwrsc is not None:
                    rwrsc.setEstimatedTime(et_from, et_to)
                    logger.debug(f":updateResources: updated {rwy} for {fid}")
                else:
                    logger.warning(f":updateResources: no reservation found for runway {rwy}")

                # 3. For flight: update runway, ramp
                ramp = self.getMeta("$.props.flight.ramp.name")
                if is_arrival:
                    et_from = et
                    et_to   = et + timedelta(minutes=150)
                else:
                    et_from = et - timedelta(minutes=150)
                    et_to   = et
                rprsc = am.ramp_allocator.findReservation(ramp, fid, self.redis)
                if rprsc is not None:
                    rprsc.setEstimatedTime(et_from, et_to)
                    logger.debug(f":updateResources: updated {ramp} for {fid}")
                else:
                    logger.warning(f":updateResources: no reservation found for ramp {ramp}")
            else:
                logger.warning(f":updateResources: count not get flight id for {self.emit_id}")

        elif self.emit_type == MOVE_TYPE.MISSION.value:
            # 4a. For others: update vehicle
            ident = self.getMeta("$.move.mission-identifier")
            vehicle = self.getMeta("move.vehicle.registration")
            am = self.managedAirport.airport.manager

            svrsc = am.equipment_allocator.findReservation(vehicle, ident, self.redis)
            if svrsc is not None:
                svrsc.setEstimatedTime(et, et)
                logger.debug(f":updateResources: updated {vehicle} for {ident}")
            else:
                logger.warning(f":updateResources: no reservation found for vehicle {vehicle}")

        elif self.emit_type == MOVE_TYPE.SERVICE.value:
            # 4b. For others: update vehicle
            ident = self.getMeta("$.move.service-identifier")
            vehicle = self.getMeta("move.vehicle.registration")
            am = self.managedAirport.airport.manager

            svrsc = am.equipment_allocator.findReservation(vehicle, ident, self.redis)
            if svrsc is not None:
                svrsc.setEstimatedTime(et, et)
                logger.debug(f":updateResources: updated {vehicle} for {ident}")
            else:
                logger.warning(f":updateResources: no reservation found for vehicle {vehicle}")

        else:
            logger.debug(f":updateResources: resources not updated")

        return (True, "ReEmit::updateResources updated")


class ReEmitAll:
    """
    Convenience wrapper to collect all ReEmits for supplied movement (Emit Meta Data)
    """
    def __init__(self, ident: str, redis):
        self.redis = redis
        self.ident = ident
        self.emits = {}

        ret = self.parseKey()
        if not ret[0]:
            logger.warning(ret[1])

        ret = self.fetch()
        if not ret[0]:
            logger.warning(ret[1])


    def parseKey(self, ident):
        valid_extensions = set(item.value for item in REDIS_TYPE)
        valid_databases = dict([(v, k) for k, v in REDIS_DATABASES.items()])

        arr = key.split(ID_SEP)

        # Do we have an extension?
        if arr[-1] != REDIS_TYPE.EMIT_META.value:
            logger.warning(f":parseKey: ({key} is not valid (extension={arr[-1]})")
            return (False, "ReEmitAll::parseKey invalid emit meta data key")

        if arr[0] not in valid_databases.keys():
            logger.warning(f":parseKey: ({key} is not valid (database={arr[0]})")
            return (False, "ReEmitAll::parseKey invalid emit key")

        self.emit_type = valid_databases[arr[0]]
        self.emit_id = ID_SEP.join(arr[1:-1])

        logger.debug(f":parseKey: {arr}: emit_type={self.emit_type}, emit_id={self.emit_id}")
        return (True, "ReEmitAll::parseKey parsed")


    def fetch(self):
        # Find all emit (different rates and queues?)
        key_base = key_path(self.ident, "*", REDIS_TYPE.EMIT)
        keys = self.redis.keys(key_base)
        if len(keys) > 0:
            for k in keys:
                key = k.decode("UTF-8")
                self.emits[key] = ReEmit(ident=key, redis=redis)
        else:
            logger.warning(f":fetch: no emission for {key_base}")
            return (False, "ReEmitAll::fetch no emission")

        # Reschedule each
        return (True, "ReEmitAll::fetch fetched")


    def emits(self):
        return self.emits
