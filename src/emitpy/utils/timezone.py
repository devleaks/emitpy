from datetime import tzinfo, timedelta
import logging

class Timezone(tzinfo):
    def __init__(self, offset:float, name: str):
        self.offset = offset
        self.name = name
    def utcoffset(self, dt):
        return timedelta(hours=self.offset)
    def tzname(self, dt):
        return self.name
    def dst(self, dt):
        return timedelta(hours=0)
