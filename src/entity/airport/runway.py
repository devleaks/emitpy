"""
Runways.

"""

from ..constants import DEPARTURE, ARRIVAL, PAX, CARGO


class Runway:  # Line, Calendar
    """
    Represents a runway with its details and its calendar for reservation
    """

    def __init__(self, name: [str], heading: float = None, width: int = None):
        self.name = name
        self.width = width
        if heading is None:
            self.heading = float(10 * int(name[0:2]))
        else:
            self.heading = heading
        self.usage = [DEPARTURE, ARRIVAL, CARGO, PAX]
        self.qfu = None


    def use(self, what: str, mode: bool = None):
        if mode is None:  # Query
            return what in self.usage

        # Else: set what
        if mode and what not in self.usage:
            self.usage.append(what)
        elif mode and what in self.usage:
            self.usage.remove(what)

        return what in self.usage

    # Aliases shortcuts
    def departure(self, mode: bool = None):
        self.use(DEPARTURE, mode)

    def arrival(self, mode: bool = None):
        self.use(ARRIVAL, mode)

    def passenger(self, mode: bool = None):
        self.use(PAX, mode)

    def cargo(self, mode: bool = None):
        self.use(CARGO, mode)
