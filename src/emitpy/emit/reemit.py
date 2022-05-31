import json
from datetime import datetime
from jsonpath import JSONPath

from .emit import EmitPoint, Emit
from emitpy.constants import FEATPROP, MOVE_TYPE, FLIGHT_PHASE, SERVICE_PHASE, MISSION_PHASE
from emitpy.constants import REDIS_DATABASE, REDIS_DATABASES, REDIS_TYPE

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
        self.redis = redis
        self.meta = None
        self.parseKey(ident, REDIS_TYPE.EMIT.value)
        res = self.load()


    def parseKey(self, emit_key: str, extension: str = None):
        """
        Tries to figure out what's being loead (type of move)
        from key root part which should be a well-known database.

        :param      emit_key:    The emit identifier
        :type       emit_key:    str
        :param      extension:  The extension
        :type       extension:  str
        """
        arr = emit_key.split(":")
        revtypes = dict([(v, k) for k, v in REDIS_DATABASES.items()])
        if arr[0] in revtypes.keys():
            self.emit_type = revtypes[arr[0]]
        else:
            self.emit_type = REDIS_DATABASE.UNKNOWN.value
            logger.warning(f":parseKey: database {arr[0]} not found ({emit_key}).")

        if extension is not None:
            if extension == arr[-1] or extension == "*":  # if it is the extention we expect
                self.emit_id = ":".join(arr[1:-1])  # remove extension
            else:
                self.emit_id = ":".join(arr[1:])    # it is not the expected extension, we leave it
                logger.warning(f":parseKey: extension {extension} not found ({emit_key}).")
        else:
            self.emit_id = ":".join(arr[1:])        # no extension to remove.
        logger.debug(f":parseKey: {arr}: emit_type={self.emit_type}, emit_id={self.emit_id}")
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
            self.meta = self.redis.json().get(emit_id)
            logger.debug(f":loadMetaFromCache: ..got {len(self.meta)} meta data")
            # logger.debug(f":loadMetaFromCache: {self.meta}")
        else:
            logger.debug(f":loadMetaFromCache: ..no meta for {emit_id}")
        return (True, "ReEmit::loadMetaFromCache loaded")


    def getMeta(self, path: str = None):
        if self.meta is None:
            ret = self.loadMetaFromCache()
            if not ret[0]:
                logger.warning(f":getMeta: load meta returned error {ret[1]}")
                return None
        if path is not None:
            return JSONPath(path).parse(self.meta)
        # return entire meta structure
        return self.meta


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
    #         val = JSONPath(path).parse(self.meta)
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


    def updateEstimatedTime(self):
        """
        We have no "original" movement but we have enough information in meta data.
        We simply augment the schedule_history with this new re-scheduling
        """
        # 1. Get the movement type and info, determine the _mark name
        emit_type = self.getMeta("$.emit-type")[0]

        ff = None
        if emit_type == MOVE_TYPE.FLIGHT.value:
            is_arrival = self.getMeta("$.move.is_arrival")[0]
            ff = FLIGHT_PHASE.TOUCH_DOWN.value if is_arrival else FLIGHT_PHASE.TAKE_OFF.value
        elif emit_type == MOVE_TYPE.SERVICE.value:
            ff = SERVICE_PHASE.SERVICE_START.value
        elif emit_type == MOVE_TYPE.MISSION.value:
            ff = MISSION_PHASE.START.value

        # 2. Get the absolute time at _mark place
        if ff is not None:
            f = self.getAbsoluteEmissionTime(ff)
            if f is not None:
                esti = datetime.fromtimestamp(f.getAbsoluteEmissionTime())
                if esti is not None:
                    ident = self.getMeta("$.ident")
                    if ident is not None:
                        # 3. Augment the schedule_history
                        self.meta["time"].append((datetime.now().isoformat(), "ET", esti.isoformat()))
                        # self.addMessage(EstimatedTimeMessage(flight_id=ident,
                        #                                      is_arrival=is_arrival,
                        #                                      et=esti))
                        logger.debug(f":updateEstimatedTime: sent new ET{'A' if is_arrival else 'D'} {ident}: {esti}")
                    else:
                        logger.warning(f":updateEstimatedTime: fcannot get ident from meta {self.meta}")
            else:
                logger.warning(":updateEstimatedTime: feature has no absolute emission time")
        else:
            logger.warning(f":updateEstimatedTime: feature at mark {ff} not found")

        # self.meta["time"].append((info_time, "ET", dt))
        # 4. Save the updated meta
        logger.debug(":updateEstimatedTime: saving new meta")
        return self.saveMeta(self.redis)

