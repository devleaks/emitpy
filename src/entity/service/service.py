"""
A Service  is a maintenance operation performed on an aircraft during a turn-around.

"""
from datetime import datetime

from .servicevehicle import ServiceVehicle


class Service:

    def __init__(self, schedule):
        self._schedule = schedule
        self.vehicle = None
        self._pos_start = None
        self._pos_end = None
        self.route = []

    def setVehicle(self, vehicle: ServiceVehicle):
        self.vehicle = vehicle

    def setSchedule(self, schedule):
        self._schedule = schedule

    def setStartPosition(self, position):
        self._pos_start = position

    def setEndPosition(self, position):
        self._pos_end = position

    def plan(self):
        # start_position -> wait_position -> service_position(ramp) -> wait_position -> end_position
        # on service road network
        return (False, "Service::plan not implemented")

    def run(self, moment: datetime):
        # set actual_datetime for plan
        return (False, "Service::run not implemented")


class FuelService(Service):

    def __init__(self, schedule: int):
        Service.__init__(self, schedule)


class CateringService(Service):

    def __init__(self, schedule: int):
        Service.__init__(self, schedule)

