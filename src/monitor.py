import datetime
import redis


class Monitor:

    def __init__(self, name: str):
        self.name = name

    def trim(self):
        pass

    def run(self):

        while True:
            r = redis.zpopmin(self.name)
            print(r)
