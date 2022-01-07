"""
A Service  is a maintenance operation performed on an aircraft during a turn-around.

"""

from ..identity import Identity
from .service_type import ServiceType
from .service_vehicle import ServiceVehicle


class Service:

    def __init__(self, srvType: ServiceType, performer: ServiceVehicle):
        self.service_type = ServiceType
        self.service_vehicle = performer


"""
start_position
end_position

service_positions = [ service_position ]
service_times = [ service_time ]
service_waits = [ service_wait ]

duration and/or quantity (+formula to compute)


"""
