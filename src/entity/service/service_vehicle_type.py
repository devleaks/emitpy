"""
A Service Vehicle Type is a type of vehicle used to perform a service or maintenance operation.

"""

from .service_type import ServiceType


class ServiceVehicleType(ServiceType):

    def __init__(self, srvType: str):
        ServiceType.__init__(self, srvType)

        self.speed = {}
        self.speed.slow = 5
        self.speed.fast = 30

        self.capacity = 1


        def service_time(self, quantity: float):
            """ Time in seconds to perform a service operation provided the supplied quantity.
            """
            return quantity