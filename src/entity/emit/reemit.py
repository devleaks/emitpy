import redis
from .emit import Emit


class ReEmit(Emit):

    def __init__(self, ident: str):
        self.ident = ident
        self.redis = redis.Redis()

    def getId(self):
        return self.ident

    def loadDB(self):
        ret = self.redis.get(self.ident)

    def move(self):
        pass

    def schedule(self):
        pass