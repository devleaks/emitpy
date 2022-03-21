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
# SERVICE VEHICLE TYPES AND MODELS
#
#
class ServiceVehicle(Identity):
    """
    A Service Vehicle Type is a type of vehicle used to perform a service or maintenance operation.

    """
    def __init__(self, registration: str, operator: Company):
        Identity.__init__(self, operator, "GSE", type(self).__name__, registration)

        self.registration = registration
        self.icao24 = None
        self.operator = operator
        self.model = None
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


# ########################
# FUEL
#
class FuelVehicle(ServiceVehicle):

    def __init__(self, registration: str, operator: Company):
        ServiceVehicle.__init__(self, registration=registration,  operator=operator)

        self.model = "ZZFA"
        self.max_capacity = 30
        self.flow = 1.0 / 60
        self.speeds = {
            "slow": 5,
            "normal": 25,
            "fast": 40
        }
        self.setup_time = 5 * 60    # in seconds


    def service_duration(self, quantity: float):
        return (2 * self.setup_time )+ quantity / self.flow  # minutes


    def refill(self):
        if self.max_capacity != inf:   # untested what happens if one refills infinity
            super().refill()

class FuelVehiclePump(FuelVehicle):

    def __init__(self, registration: str, operator: Company):
        FuelVehicle.__init__(self, registration=registration,  operator=operator)
        self.model = "ZZFA"
        self.max_capacity = inf
        self.flow = 2.0 / 60
        self.speeds = {
            "slow": 5,
            "normal": 30,
            "fast": 60
        }
        self.setup_time = 5 * 60    # in seconds


class FuelVehicleTankerLarge(FuelVehicle):

    def __init__(self, registration: str, operator: Company):
        FuelVehicle.__init__(self, registration=registration,  operator=operator)
        self.model = "ZZFB"
        self.max_capacity = 40
        self.flow = 1.5 / 60
        self.speeds = {
            "slow": 5,
            "normal": 20,
            "fast": 40
        }
        self.setup_time = 5 * 60    # in seconds


class FuelVehicleTankerMedium(FuelVehicle):

    def __init__(self, registration: str, operator: Company):
        FuelVehicle.__init__(self, registration=registration,  operator=operator)
        self.model = "ZZFC"
        self.max_capacity = 20
        self.flow = 0.9 / 60
        self.speeds = {
            "slow": 5,
            "normal": 20,
            "fast": 50
        }
        self.setup_time = 4 * 60    # in seconds


# ########################
# CATERING
#
class CateringVehicle(ServiceVehicle):

    def __init__(self, registration: str, operator: Company):
        ServiceVehicle.__init__(self, registration=registration,  operator=operator)
        self.model = "ZZCA"
        self.setup_time = 4
        self.flow = 1/20


# ########################
# CLEANING
#
class CleaningVehicle(ServiceVehicle):

    def __init__(self, registration: str, operator: Company):
        ServiceVehicle.__init__(self, registration=registration,  operator=operator)
        self.model = "ZZKA"
        self.setup_time = 4
        self.flow = 1/20


# ########################
# SEWAGE
#
class SewageVehicle(ServiceVehicle):

    def __init__(self, registration: str, operator: Company):
        ServiceVehicle.__init__(self, registration=registration,  operator=operator)
        self.model = "ZZSA"
        self.setup_time = 4
        self.flow = 1/20


# ########################
# WATER
#
class WaterVehicle(ServiceVehicle):

    def __init__(self, registration: str, operator: Company):
        ServiceVehicle.__init__(self, registration=registration,  operator=operator)
        self.model = "ZZWA"
        self.setup_time = 4
        self.flow = 1/20


# ########################
# CARGO
#
class ULDVehicle(ServiceVehicle):

    def __init__(self, registration: str, operator: Company):
        ServiceVehicle.__init__(self, registration=registration,  operator=operator)
        self.model = "ZZUA"
        self.setup_time = 4
        self.flow = 1


# ########################
# BAGGAGE
#
class BaggageVehicle(ServiceVehicle):

    def __init__(self, registration: str, operator: Company):
        ServiceVehicle.__init__(self, registration=registration,  operator=operator)
        self.model = "ZZBA"
        self.setup_time = 1
        self.flow = 10

class BaggageVehicleLoader(BaggageVehicle):

    def __init__(self, registration: str, operator: Company):
        FuelVehicle.__init__(self, registration=registration,  operator=operator)
        self.model = "ZZBL"
        self.max_capacity = inf
        self.flow = 1
        self.speeds = {
            "slow": 5,
            "normal": 30,
            "fast": 50
        }
        self.setup_time = 2 * 60    # in seconds


class BaggageVehicleTrain(BaggageVehicle):

    def __init__(self, registration: str, operator: Company):
        FuelVehicle.__init__(self, registration=registration,  operator=operator)
        self.model = "ZZBT"
        self.max_capacity = 50
        self.flow = 10 / 60
        self.speeds = {
            "slow": 3,
            "normal": 10,
            "fast": 20
        }
        self.setup_time = 0    # in seconds


class BaggageVehicleTrain2(BaggageVehicle):

    def __init__(self, registration: str, operator: Company):
        FuelVehicle.__init__(self, registration=registration,  operator=operator)
        self.model = "ZZBU"
        self.max_capacity = 100
        self.flow = 10 / 60
        self.speeds = {
            "slow": 3,
            "normal": 10,
            "fast": 20
        }
        self.setup_time = 0    # in seconds


# ########################
# CREW (Cabin & Flight)
#
class CrewBus(ServiceVehicle):

    def __init__(self, registration: str, operator: Company):
        ServiceVehicle.__init__(self, registration=registration,  operator=operator)
        self.model = "ZZAK"
        self.setup_time = 4
        self.flow = 1


class CrewLimousine(ServiceVehicle):

    def __init__(self, registration: str, operator: Company):
        ServiceVehicle.__init__(self, registration=registration,  operator=operator)
        self.model = "ZZAJ"
        self.setup_time = 4
        self.flow = 1


# ########################
# PASSENGERS (VIP to Economy)
#
class PassengerBus(ServiceVehicle):

    def __init__(self, registration: str, operator: Company):
        ServiceVehicle.__init__(self, registration=registration,  operator=operator)
        self.model = "ZZAB"
        self.setup_time = 4
        self.flow = 1


class PassengerLimousine(ServiceVehicle):

    def __init__(self, registration: str, operator: Company):
        ServiceVehicle.__init__(self, registration=registration,  operator=operator)
        self.model = "ZZAL"
        self.setup_time = 4
        self.flow = 1


# ########################
# AIRCRAFT SUPPORT
#
class AircraftAPU(ServiceVehicle):

    def __init__(self, registration: str, operator: Company):
        ServiceVehicle.__init__(self, registration=registration,  operator=operator)
        self.model = "ZZAA"
        self.setup_time = 4
        self.flow = 1

class AircraftACU(ServiceVehicle):

    def __init__(self, registration: str, operator: Company):
        ServiceVehicle.__init__(self, registration=registration,  operator=operator)
        self.model = "ZZAC"
        self.setup_time = 4
        self.flow = 1


# ########################
# AIPORT SUPPORT
#
class AirportSecurity(ServiceVehicle):

    def __init__(self, registration: str, operator: Company):
        ServiceVehicle.__init__(self, registration=registration,  operator=operator)
        self.model = "ZZAS"
        self.setup_time = 4
        self.flow = 1


class AirportEmergency(ServiceVehicle):

    def __init__(self, registration: str, operator: Company):
        ServiceVehicle.__init__(self, registration=registration,  operator=operator)
        self.model = "ZZAE"
        self.setup_time = 4
        self.flow = 1


class AirportFire(ServiceVehicle):

    def __init__(self, registration: str, operator: Company):
        ServiceVehicle.__init__(self, registration=registration,  operator=operator)
        self.model = "ZZAF"
        self.setup_time = 4
        self.flow = 1
        # May create a few subtypes later...

