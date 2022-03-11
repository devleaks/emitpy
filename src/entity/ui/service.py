"""
Wrapper for web API
"""
from .requestapi import SimRequest


class ServiceRequest(SimRequest):

    def __init__(self, operator: str, flight: str, scheduled: str, service: str, ramp: str, icao24: str,
                 model: str=None, startpos: str=None, endpos: str=None):
        SimRequest.__init__(self)
