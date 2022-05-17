import json
from jsonpath import JSONPath

from .emit import EmitPoint, Emit
from emitpy.constants import FEATPROP, REDIS_DATABASES, REDIS_TYPE
from emitpy.parameters import REDIS_CONNECT

import logging

logger = logging.getLogger("ReEmit")


class ReEmit(Emit):
    """
    Loads previsously saved Emit output and compute new emission points
    based on new schedule or added pauses.
    """
    def __init__(self, ident: str, redis):
        Emit.__init__(self, move=None)
        self.redis = redis
        self.parseKey(ident, REDIS_TYPE.EMIT.value)
        self.load()


    def parseKey(self, emit_id: str, extension: str = None):
        """
        Tries to figure out what's being loead (type of move)
        from key root part which should be a well-known database.

        :param      emit_id:    The emit identifier
        :type       emit_id:    str
        :param      extension:  The extension
        :type       extension:  str
        """
        arr = emit_id.split(":")
        revtypes = dict([(v, k) for k, v in REDIS_DATABASES.items()])
        if arr[0] in revtypes.keys():
            self.emit_type = revtypes[arr[0]]
        else:
            self.emit_type = "unknowndb"
            logger.warning(f":parseKey: database {arr[0]} not found ({emit_id}).")

        if extension is not None:
            if extension == arr[-1] or extension == "*":  # if it is the extention we expect
                self.emit_id = ":".join(arr[1:-1])  # remove extension
            else:
                self.emit_id = ":".join(arr[1:])    # it is not the expected extension, we leave it
        else:
            self.emit_id = ":".join(arr[1:])        # no extension to remove.
        logger.debug(f":parseKey: {arr}: emit_type={self.emit_type} : emit_id={self.emit_id}")


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

        status = self.parseMeta()
        if not status[0]:
            return status

        return (True, "ReEmit::load loaded")


    def loadFromCache(self):
        def toEmitPoint(s: str):
            f = json.loads(s.decode('UTF-8'))
            return EmitPoint.new(f)

        emit_id = self.getKey(REDIS_TYPE.EMIT.value)
        logger.debug(f":loadFromCache: trying to read {emit_id}..")
        ret = self.redis.zrange(emit_id, 0, -1)
        logger.debug(f":loadFromCache: ..got {len(ret)} members")
        self._emit = [toEmitPoint(f) for f in ret]
        logger.debug(f":loadFromCache: collected {len(self._emit)} points")
        return (True, "ReEmit::loadFromCache loaded")


    def loadMetaFromCache(self):
        emit_id = self.getKey(REDIS_TYPE.EMIT_META.value)
        if self.redis.exists(emit_id):
            self.meta = self.redis.json().get(emit_id)
            logger.debug(f":loadMeta: ..got {len(self.meta)} meta data")
        else:
            logger.debug(f":loadMeta: ..no meta for {emit_id}")
        return (True, "ReEmit::loadMetaFromCache loaded")


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


    def parseMeta(self):
        """
        Reinstall meta data in Emit object based on its type (flight, service, mission).
        Each meta data is carefully extracted from a JSON path.
        """
        def getMeta(path: str):
            val = JSONPath(path).parse(self.meta)
            if val is None:
                logger.warning(f":parseMeta: no value for {path}")
            return val

        if self.emit_type == "flight":
            pass
        elif self.emit_type == "service":
            pass
        elif self.emit_type == "misssion":
            pass
        else:
            logger.warning(f":parseMeta: invalid type {self.emit_type}")

        return (True, "ReEmit::parseMeta loaded")
