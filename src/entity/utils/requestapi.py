"""
"""
import json

class FlightRequest:

    def __init__(self, flight: str, scheduled: str, apt_from: str, apt_to: str, actype: str, ramp: str, icao24: str,
                 acreg: str=None, runway: str=None):
        pass

class ServiceRequest:

    def __init__(self, flight: str, scheduled: str, service: str, ramp: str, icao24: str,
                 model: str=None, startpos: str=None, endpos: str=None):
        pass


class EmitRequest:

    def __init__(self, ident: str, sync_name: str, sync_time: str):
        pass

    def run(self):
        return {
            "errno": 0,
            "errmsg": "no error",
            "data": "no data"
        }

class StartQueueRequest:

    def __init__(self, name: str, sync_time: str, speed: float=1):
        pass


class StopQueueRequest:

    def __init__(self, name: str):
        pass
