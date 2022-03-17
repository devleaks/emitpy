"""
A Service Vehicle is a vehicle used to perform a service or maintenance operation.
It has a Service Vehicle Type that is ued to represent it.
"""
import logging
from math import inf

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
        self.icao24 = None
        self.operator = operator
        self.model = model

        self.position = None

        self.speed = {
            "slow": 5/3.6,       # km/h to m/s
            "normal": 30/3.6,
            "fast": 50/3.6,
        }

        self.max_capacity = 1
        self.current_load = 0

        self.setup_time = 0
        self.flow = 1  # quantity per minutes

    def getId(self):
        return self.name  # registration

    def getInfo(self):
        return {
            "registration": self.registration,
            "icao24": self.icao24,
            "operator": self.operator.getInfo(),
            "service": type(self).__name__.replace("Vehicle", "").lower(),  # a try...
            "model": self.model
        }

    def setICAO24(self, icao24):
        self.icao24 = icao24

    def setPosition(self, position):
        self.position = position

    def getPosition(self):
        return self.position

    def refill(self, quantity: float=None):
        """
        Refills truck of at most quantity and returns refill time.

        :param      quantity:  The quantity
        :type       quantity:  float
        """
        if quantity is None:
            refill_quantity = self.max_capacity -  self.current_load
        else:
            refill_quantity = quantity

        if self.current_load + refill_quantity > self.max_capacity:
            self.current_load = self.max_capacity
            # warning exceeds
        else:
            self.current_load = self.current_load + refill_quantity

        refill_time = self.setup_time + refill_quantity * self.quantity_time  # assumes service and refill at same speed
        return refill_time

    def service_duration(self, quantity: float):
        """
        Time in seconds to perform a service operation provided the supplied quantity.
        """
        return self.setup_time + quantity / self.flow

    def service(self, quantity: float=None):
        """
        Serve quantity. Returns quantity served.
        """
        if quantity is None:
            logger.debug(f":service: served {self.current_load:f}.")
            served = self.current_load
            self.current_load = 0
        elif self.current_load > quantity:
            self.current_load = self.current_load - quantity
            served = quantity
            logger.debug(f":service: served {quantity:f}. {self.current_load:f} remaning")
        else:
            served = self.current_load
            logger.warning(f":service: can only serve {self.current_load:f} out of {quantity:f}. {quantity - self.current_load:f} remaning to serve")
            self.current_load = 0

        return served


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
        if model in FuelVehicle.MODELS:
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
        self.flow = self.flow / 60  # in seconds
        self.setup_time = 5 * 60    # in seconds

    def service_duration(self, quantity: float):
        return (2 * self.setup_time )+ quantity / self.flow  # minutes


    def refill(self):
        if self.max_capacity != inf:   # untested what happens if one refills infinity
            super().refill()


class CateringVehicle(ServiceVehicle):

    def __init__(self, registration: str, operator: Company, model: str = None):
        ServiceVehicle.__init__(self, registration=registration,  operator=operator,  model=model)
        self.setup_time = 8
        self.flow = 1/20


class CleaningVehicle(ServiceVehicle):

    def __init__(self, registration: str, operator: Company, model: str = None):
        ServiceVehicle.__init__(self, registration=registration,  operator=operator,  model=model)


class SewageVehicle(ServiceVehicle):

    def __init__(self, registration: str, operator: Company, model: str = None):
        ServiceVehicle.__init__(self, registration=registration,  operator=operator,  model=model)


class WaterVehicle(ServiceVehicle):

    def __init__(self, registration: str, operator: Company, model: str = None):
        ServiceVehicle.__init__(self, registration=registration,  operator=operator,  model=model)


class ULDVehicle(ServiceVehicle):

    def __init__(self, registration: str, operator: Company, model: str = None):
        ServiceVehicle.__init__(self, registration=registration,  operator=operator,  model=model)


class BaggageVehicle(ServiceVehicle):

    def __init__(self, registration: str, operator: Company, model: str = None):
        ServiceVehicle.__init__(self, registration=registration,  operator=operator,  model=model)

