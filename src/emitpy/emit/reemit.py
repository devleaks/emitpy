import json
from datetime import datetime, timedelta
from jsonpath import JSONPath

from .emit import EmitPoint, Emit
from emitpy.message import Messages, EstimatedTimeMessage
from emitpy.constants import FEATPROP, MOVE_TYPE, FLIGHT_PHASE, SERVICE_PHASE, MISSION_PHASE
from emitpy.constants import REDIS_DATABASE, REDIS_DATABASES, REDIS_TYPE
from emitpy.utils import Timezone

import logging

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

        ret = self.parseKey(ident, REDIS_TYPE.EMIT.value)
        if not ret[0]:
            logger.warning(f":init: could not parse {ident}")

        ret = self.load()
        if not ret[0]:
            logger.warning(f":init: could not load {ident}")


    def setManagedAirport(self, airport):
        self.managedAirport = airport


    def parseKey(self, emit_key: str, extension: str = None):
        """
        Tries to figure out what's being loaded (type of move)
        from key root part which should be a well-known database.
        Extract frequency from key to allow for same move with several emission frequency.

        :param      emit_key:    The emit identifier
        :type       emit_key:    str
        :param      extension:  The extension
        :type       extension:  str
        """
        valid_extensions = set(item.value for item in REDIS_TYPE)
        if extension not in valid_extensions:
            logger.warning(f":parseKey: extension {extension} not in set {valid_extensions}.")

        arr = emit_key.split(":")
        revtypes = dict([(v, k) for k, v in REDIS_DATABASES.items()])
        if arr[0] in revtypes.keys():
            self.emit_type = revtypes[arr[0]]
        else:
            self.emit_type = REDIS_DATABASE.UNKNOWN.value
            logger.warning(f":parseKey: database {arr[0]} not found ({emit_key}).")

        if extension is not None:
            if extension == arr[-1]:  # if it is the extention we expect
                self.emit_id = ":".join(arr[1:-2])  # remove extension and frequency
            elif extension == "*" and arr[-1] in valid_extensions:
                logger.debug(f":parseKey: removed extension {arr[-1]}.")
                self.emit_id = ":".join(arr[1:-2])  # remove extension and frequency
            else:
                if arr[-1] in valid_extensions:
                    logger.warning(f":parseKey: {emit_key} has valid extension {arr[-1]} (not removed).")
                self.emit_id = ":".join(arr[1:-1])    # it is not the expected extension, we leave it but remove frequency
                logger.warning(f":parseKey: extension {extension} not found ({emit_key}).")
        else:
            self.emit_id = ":".join(arr[1:-1])        # no extension to remove, remove frequency.
            self.frequency = int(arr[-1])
        logger.debug(f":parseKey: {arr}: emit_type={self.emit_type}, emit_id={self.emit_id}, frequency={self.frequency}")
        return (True, "ReEmit::parseKey parsed")


    def load(self):
        status = self.loadFromCache()
        if not status[0]:
            return status

        status = self.extractMove()
        if not status[0]:
            return status

        status = self.loadMetaFromCache()
        if not status[0]:
            return status

        # status = self.parseMeta()
        # if not status[0]:
        #     return status

        return (True, "ReEmit::load loaded")


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


    def loadMetaFromCache(self):
        emit_id = self.getKey(REDIS_TYPE.EMIT_META.value)
        logger.debug(f":loadMetaFromCache: trying to read {emit_id}..")
        if self.redis.exists(emit_id):
            self.emit_meta = self.redis.json().get(emit_id)
            logger.debug(f":loadMetaFromCache: ..got {len(self.emit_meta)} meta data")
            # logger.debug(f":loadMetaFromCache: {self.emit_meta}")
        else:
            logger.debug(f":loadMetaFromCache: ..no meta for {emit_id}")
        return (True, "ReEmit::loadMetaFromCache loaded")


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
        basename = os.path.join(AODB_DIR, FLIGHT_DATABASE, emit_id)

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
                localtz = Timezone(offset=self.managedAirport._this_airport["tzoffset"], name=self.managedAirport._this_airport["tzname"])
                return datetime.fromtimestamp(f, tz=localtz)
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
                self.addMessage(EstimatedTimeMessage(flight_id=fid,
                                                     is_arrival=is_arrival,
                                                     et=et))
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

            svrsc = am.vehicle_allocator.findReservation(vehicle, ident, self.redis)
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

            svrsc = am.vehicle_allocator.findReservation(vehicle, ident, self.redis)
            if svrsc is not None:
                svrsc.setEstimatedTime(et, et)
                logger.debug(f":updateResources: updated {vehicle} for {ident}")
            else:
                logger.warning(f":updateResources: no reservation found for vehicle {vehicle}")

        else:
            logger.debug(f":updateResources: resources not updated")

        return (True, "ReEmit::updateResources updated")
