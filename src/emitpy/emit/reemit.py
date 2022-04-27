import json

from .emit import EmitPoint, Emit
from ..constants import FEATPROP, REDIS_DATABASE, REDIS_TYPE
from ..parameters import REDIS_CONNECT

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
        self.parseDBKey(ident)
        # self.ident = ident
        self.loadDB()
        self.loadMove()


    def getId(self):
        return self.ident


    def loadDB(self):
        def toEmitPoint(s: str):
            f = json.loads(s.decode('UTF-8'))
            return EmitPoint.new(f)

        emit_id = self.dbKey(REDIS_TYPE.EMIT.value)
        logger.debug(f":loadDB: trying to read {emit_id}..")
        ret = self.redis.zrange(emit_id, 0, -1)
        logger.debug(f":loadDB: ..got {len(ret)} members")
        self._emit = [toEmitPoint(f) for f in ret]
        logger.debug(f":loadDB: collected {len(self._emit)} points")


    def loadMove(self):
        self.moves = list(filter(lambda f: not f.getProp(FEATPROP.BROADCAST.value), self._emit))


    def loadProps(self):
        emit_id = self.dbKey(REDIS_TYPE.EMIT_META.value)
        if self.redis.exists(emit_id):
            self.redis = json.loads(redis.get(emit_id))
            logger.debug(f":loadDB: ..got {len(self.props)} props")
        else:
            logger.debug(f":loadDB: ..no meta for {emit_id}")
