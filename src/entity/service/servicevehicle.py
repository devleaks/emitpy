"""
A Service Vehicle is a vehicle used to perform a service or maintenance operation.
It has a Service Vehicle Type that is ued to represent it.
"""
import logging
from math import inf

from ..constants import SERVICE
from ..business import Identity, Company

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("ServiceVehicle")


#####################################
# SERVICE VEHICLET TYPES
#
#
class ServiceVehicle(Identity):
    """
    A Service Vehicle Type is a type of vehicle used to perform a service or maintenance operation.

    """
    def __init__(self, registration: str, operator: Company, model: str = None):
        Identity.__init__(self, operator, "GSE", type(self).__name__, registration)

        self.registration = registration
        self.operator = operator

        self.models = []

        self.max_capacity = 30
        self.current_load = 0

        self.speed = {
            "slow": 5,
            "normal": 30,
            "fast": 50
        }

        self.setup_time = 0
        self.service_time = 0
        self.flow = 1

        self.mapicons = {}
        self.models3d = {}

    def refill(self, quantity: float=None):
        """
        Time in seconds to perform a service operation provided the supplied quantity.
        """
        if quantity is None or self.current_load + quantity > self.max_capacity:
            self.current_load = self.max_capacity
        else:
            self.current_load = self.current_load + quantity

    def service_time(self, quantity: float):
        return 0

    def service(self, quantity: float=None):
        """
        Time in seconds to perform a service operation provided the supplied quantity.
        """
        if quantity is None or quantity > self.current_load:
            self.current_load = 0
        else:
            self.current_load = self.current_load - quantity

        return self.service_time(quantity)


class CleaningVehicle(ServiceVehicle):

    def __init__(self, registration: str, operator: Company, model: str = None):
        ServiceVehicle.__init__(self, registration=registration,  operator=operator,  model=model)


class SewageVehicle(ServiceVehicle):

    def __init__(self, registration: str, operator: Company, model: str = None):
        ServiceVehicle.__init__(self, registration=registration,  operator=operator,  model=model)


class CateringVehicle(ServiceVehicle):

    def __init__(self, registration: str, operator: Company, model: str = None):
        ServiceVehicle.__init__(self, registration=registration,  operator=operator,  model=model)
        self.setup_time = 8
        self.service_time = 10

    def service_time(self, quantity: float):
        return self.setup_time + self.service_time  # minutes


class WaterVehicle(ServiceVehicle):

    def __init__(self, registration: str, operator: Company, model: str = None):
        ServiceVehicle.__init__(self, registration=registration,  operator=operator,  model=model)


class FuelVehicle(ServiceVehicle):

    MODELS = ["pump", "tanker-large", "tanker-medium"]

    def __init__(self, registration: str, operator: Company, model: str = None):
        ServiceVehicle.__init__(self, registration=registration,  operator=operator,  model=model)

        self.flow = 1
        SPEEDS = {
            "pump": {
                "slow": 5,
                "normal": 30,
                "fast": 50
            },
            "tanker-large": {
                "slow": 3,
                "normal": 25,
                "fast": 40
            },
            "tanker-medium": {
                "slow": 5,
                "normal": 30,
                "fast": 50
            }
        }
        if model in self.models:
            self.speeds = SPEEDS[model]
        if model == "pump":
            self.max_capacity = inf
            self.flow = 0.9
        if model == "tanker-large":
            self.max_capacity = 30
            self.flow = 0.8
        if model == "tanker-medium":
            self.max_capacity = 15
            self.flow = 0.7
        self.setup_time = 8

    def service_time(self, quantity: float):
        return self.setup_time + quantity / self.flow  # minutes


    def refill(self):
        if self.max_capacity != inf:   # untested what happens if one refills infinity
            super().refill()


class ULDVehicle(ServiceVehicle):

    def __init__(self, registration: str, operator: Company, model: str = None):
        ServiceVehicle.__init__(self, registration=registration,  operator=operator,  model=model)


class BaggageVehicle(ServiceVehicle):

    def __init__(self, registration: str, operator: Company, model: str = None):
        ServiceVehicle.__init__(self, registration=registration,  operator=operator,  model=model)

