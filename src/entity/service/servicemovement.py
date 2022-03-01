"""
Build movement of a service vehicle
"""
import os
import json
import logging
from math import pi
import copy

from geojson import Point, LineString, FeatureCollection, Feature
from turfpy.measurement import distance, destination, bearing

from ..airport import AirportBase
from ..flight import MovePoint, Movement
from ..service import Service, ServiceVehicle

class ServiceMove(Movement):
    """
    Movement build the detailed path of the aircraft, both on the ground (taxi) and in the air,
    from takeoff to landing and roll out.
    """
    def __init__(self, service: Flight, airport: AirportBase):
        Movement.__init__(self, airport=airport)


    def load(self):
        pass


    def save(self):
        pass


    def make(self):
        pass


