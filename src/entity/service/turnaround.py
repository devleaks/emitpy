"""
A Turnaround is a collection of Services to be performed on an aircraft during a turn-around.

"""
import Service


class Turnaround:

    def __init__(self, srvs: [Service]):
        self.services = srvs
