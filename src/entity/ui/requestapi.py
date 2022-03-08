"""
Wrapper for web API
"""


class SimRequest:

    def __init__(self):
        pass

    def run(self):
        return {
            "errno": 1,
            "errmsg": type(self).__name__ + " not implemented",
            "data": ""
        }

class FlightRequest(SimRequest):

    def __init__(self, airline: str, flight: str, scheduled: str, apt_from: str, apt_to: str, actype: str, ramp: str, icao24: str,
                 acreg: str=None, runway: str=None):
        SimRequest.__init__(self)

class ServiceRequest(SimRequest):

    def __init__(self, operator: str, flight: str, scheduled: str, service: str, ramp: str, icao24: str,
                 model: str=None, startpos: str=None, endpos: str=None):
        SimRequest.__init__(self)


class EmitRequest(SimRequest):

    def __init__(self, ident: str, sync_name: str, sync_time: str):
        SimRequest.__init__(self)

class StartQueueRequest(SimRequest):

    def __init__(self, name: str, sync_time: str, speed: float=1):
        SimRequest.__init__(self)


class StopQueueRequest(SimRequest):

    def __init__(self, name: str):
        SimRequest.__init__(self)
