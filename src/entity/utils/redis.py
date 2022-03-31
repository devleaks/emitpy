import redis

from ..constants import REDIS_DATABASE, REDIS_QUEUE

class RedisUtils:

    def __init__(self):
        self.redis = redis.Redis()

    def list_emits(self):
        suffix = "-enqueued"
        keys = self.redis.keys("*"+suffix)
        return [(k.decode("utf-8"), k.decode("utf-8").replace(suffix, "")) for k in sorted(keys)]

    def list_queues(self):
        return ("none", "none")

    def create_queue(self, name:str , fmt: str, start: str, speed: float):
        pass

    def delete_queue(self, name:str):
        pass

    def dashboard(self):
        pass

    def inc(self, name:str, val: int = 1):
        pass
