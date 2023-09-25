# Special timezone handling for Python
from datetime import tzinfo, timedelta


class Timezone(tzinfo):
    """
    Creates a named Timezone
    """

    def __init__(self, offset: float, name: str):
        self.offset = offset
        self.name = name

    def utcoffset(self, dt):
        return timedelta(hours=self.offset)

    def tzname(self, dt):
        return self.name

    def dst(self, dt):
        return timedelta(hours=0)
