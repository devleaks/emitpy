import redis
import json

from .emit import EmitPoint, Emit
from ..constants import FEATPROP

import logging

logger = logging.getLogger("ReEmit")


class ReEmit(Emit):
    """
    Loads previsously saved Emit output and compute new emission points
    based on new schedule or added pauses.
    """

    def __init__(self, ident: str):
        Emit.__init__(self, move=None)
        self.ident = ident
        self.redis = redis.Redis()

        self.loadDB()
        self.loadMove()


    def getId(self):
        return self.ident


    def loadDB(self):

        def toEmitPoint(s: str):
            f = json.loads(s.decode('UTF-8'))
            return EmitPoint(geometry=f["geometry"], properties=f["properties"])

        logger.debug(f":loadDB: trying to read {self.ident}..")
        ret = self.redis.zrange(self.ident, 0, -1)
        logger.debug(f":loadDB: like {ret[0]}")
        logger.debug(f":loadDB: ..got {len(ret)} members")
        self._emit = [toEmitPoint(f) for f in ret]
        logger.debug(f":loadDB: like {self._emit[0]}")


    def loadMove(self):
        self.moves = list(filter(lambda f: not f.getProp(FEATPROP.BROADCAST.value), self._emit))
