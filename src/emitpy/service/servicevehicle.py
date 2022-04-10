"""
A Service Vehicle is a vehicle used to perform a service or maintenance operation.
It has a Service Vehicle Type that is ued to represent it.
"""
import logging
from math import inf

from ..business import Identity, Company
from ..constants import SERVICE

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

        self.operator = operator
        self.registration = registration
        self.icao = "ZZZC"  # "ICAO" model name, should be ZZZC for all ground vehicle, but we use ZZZA->ZZZZ

        self.icao24 = None
        self.callsign = None

        self.model = ""
        self.model_name = "Generic GSE Vehicle"

        self.position = None
        self.next_position = None

        self.speed = {
            "slow": 5/3.6,       # km/h to m/s
            "normal": 30/3.6,
            "fast": 50/3.6,
        }

        self.max_capacity = 1
        self.current_load = 0

        self.setup_time = 0
        self.flow = 1  # quantity per minutes

    @staticmethod
    def getCombo():
        # No meta code introspection! vehicle types (and models) are manually hardcoded.
        a = []
        for s in SERVICE:
            if s.value == "fuel":
                a.append(("pump", "Fuel Jet Pump"))
                a.append(("tanker_large", "Large Fuel Tanker"))
                a.append(("tanker_medium", "Medium Fuel Tanker"))
            else:
                a.append((s.value+":default", s.value[0].upper()+s.value[1:]+" Vehicle"))
        return a

    def getId(self):
        return self.name  # registration

    def getInfo(self):
        return {
            "icao": self.icao,
            "registration": self.registration,
            "callsign": self.registration,
            "icao24": self.icao24,
            "operator": self.operator.getInfo(),
            "service": type(self).__name__.replace("Vehicle", "").lower(),  # a try..., not 100% correct
            "model": self.model,
            "model_name": self.model_name
        }

    def setICAO24(self, icao24):
        self.icao24 = icao24

    def setPosition(self, position):
        self.position = position

    def setNextPosition(self, position):
        self.next_position = position


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

        return self.service_duration(refill_quantity)

    def empty(self, quantity: float=None):
        """
        Empties a truck of its load and returns empting/unloading time.

        :param      quantity:  The quantity
        :type       quantity:  float
        """
        if quantity is None:
            empty_quantity = self.current_load
        else:
            empty_quantity = quantity

        if self.current_load < empty_quantity:
            self.current_load = 0
        else:
            self.current_load = self.current_load - empty_quantity

        return self.service_duration(empty_quantity)

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

        self.icao = "ZZZE"
        self.model = ""
        self.model_name = "Generic fuel vehicle (medium size tanker)"
        self.max_capacity = 20
        self.flow = 0.9 / 60
        self.speeds = {
            "slow": 5,
            "normal": 20,
            "fast": 50
        }
        self.setup_time = 4 * 60    # in seconds

    def service_duration(self, quantity: float):
        return (2 * self.setup_time )+ quantity / self.flow  # minutes

    def refill(self):
        if self.max_capacity != inf:   # untested what happens if one refills infinity
            super().refill()


class FuelVehiclePump(FuelVehicle):

    def __init__(self, registration: str, operator: Company):
        FuelVehicle.__init__(self, registration=registration,  operator=operator)
        self.icao = "ZZZF"
        self.model = "pump"
        self.model_name = "Fuel hydrant vehicle"
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
        self.icao = "ZZZG"
        self.model = "tanker-large"
        self.model_name = "Fuel tanker large"
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
        self.icao = "ZZZE"
        self.model = "tanker-medium"
        self.model_name = "Fuel tanker medium"
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
        self.icao = "ZZZH"
        self.model = ""
        self.model_name = "Catering vehicle"
        self.setup_time = 4
        self.flow = 1/20


# ########################
# CLEANING
#
class CleaningVehicle(ServiceVehicle):

    def __init__(self, registration: str, operator: Company):
        ServiceVehicle.__init__(self, registration=registration,  operator=operator)
        self.icao = "ZZZX"
        self.model = ""
        self.model_name = "Cleaning vehicle"
        self.setup_time = 4
        self.flow = 1/20


# ########################
# SEWAGE
#
class SewageVehicle(ServiceVehicle):

    def __init__(self, registration: str, operator: Company):
        ServiceVehicle.__init__(self, registration=registration,  operator=operator)
        self.icao = "ZZZV"
        self.model = ""
        self.model_name = "Sewage vehicle"
        self.setup_time = 4
        self.flow = 1/20


# ########################
# WATER
#
class WaterVehicle(ServiceVehicle):

    def __init__(self, registration: str, operator: Company):
        ServiceVehicle.__init__(self, registration=registration,  operator=operator)
        self.icao = "ZZZW"
        self.model = ""
        self.model_name = "Water vehicle"
        self.setup_time = 4
        self.flow = 1/20


# ########################
# CARGO
#
class CargoVehicle(ServiceVehicle):

    def __init__(self, registration: str, operator: Company):
        ServiceVehicle.__init__(self, registration=registration,  operator=operator)
        self.icao = "ZZZU"
        self.model = ""
        self.model_name = "Cargo mover vehicle"
        self.setup_time = 4
        self.flow = 1


class CargoVehicleUld(ServiceVehicle):

    def __init__(self, registration: str, operator: Company):
        ServiceVehicle.__init__(self, registration=registration,  operator=operator)
        self.icao = "ZZZT"
        self.model = "uld"
        self.model_name = "Cargo ULD lift"
        self.setup_time = 4
        self.flow = 1


# ########################
# BAGGAGE
#
class BaggageVehicle(ServiceVehicle):

    def __init__(self, registration: str, operator: Company):
        ServiceVehicle.__init__(self, registration=registration,  operator=operator)
        self.icao = "ZZZB"
        self.model = ""
        self.model_name = "Baggage train"
        self.setup_time = 1
        self.flow = 10

class BaggageVehicleBelt(BaggageVehicle):

    def __init__(self, registration: str, operator: Company):
        FuelVehicle.__init__(self, registration=registration,  operator=operator)
        self.icao = "ZZZB"
        self.model = "belt"
        self.model_name = "Baggage belt vehicle"
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
        self.icao = "ZZZD"
        self.model = "train"
        self.model_name = "Baggage train"
        self.max_capacity = 50
        self.flow = 10 / 60
        self.speeds = {
            "slow": 3,
            "normal": 10,
            "fast": 20
        }
        self.setup_time = 0    # in seconds


class BaggageVehicleTrainSmall(BaggageVehicle):

    def __init__(self, registration: str, operator: Company):
        FuelVehicle.__init__(self, registration=registration,  operator=operator)
        self.icao = "ZZZI"
        self.model = "train-small"
        self.model_name = "Baggage train (small)"
        self.max_capacity = 100
        self.flow = 10 / 60
        self.speeds = {
            "slow": 3,
            "normal": 10,
            "fast": 20
        }
        self.setup_time = 0    # in seconds


class BaggageVehicleTrainLarge(BaggageVehicle):

    def __init__(self, registration: str, operator: Company):
        FuelVehicle.__init__(self, registration=registration,  operator=operator)
        self.icao = "ZZZJ"
        self.model = "train-large"
        self.model_name = "Baggage train (large)"
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
class CrewVehicle(ServiceVehicle):

    def __init__(self, registration: str, operator: Company):
        ServiceVehicle.__init__(self, registration=registration,  operator=operator)
        self.icao = "ZZZK"
        self.model = ""
        self.model_name = "Crew bus"
        self.setup_time = 4
        self.flow = 1


class CrewVehicleBus(ServiceVehicle):

    def __init__(self, registration: str, operator: Company):
        ServiceVehicle.__init__(self, registration=registration,  operator=operator)
        self.icao = "ZZZK"
        self.model = "bus"
        self.model_name = "Crew bus"
        self.setup_time = 4
        self.flow = 1


class CrewVehicleLimousine(ServiceVehicle):

    def __init__(self, registration: str, operator: Company):
        ServiceVehicle.__init__(self, registration=registration,  operator=operator)
        self.icao = "ZZZL"
        self.model = "limousine"
        self.model_name = "Crew limousine"
        self.setup_time = 4
        self.flow = 1


# ########################
# PASSENGERS (VIP to Economy)
#
class PassengerVehicle(ServiceVehicle):

    def __init__(self, registration: str, operator: Company):
        ServiceVehicle.__init__(self, registration=registration,  operator=operator)
        self.icao = "ZZZQ"
        self.model = ""
        self.model_name = "Passenger coach"
        self.setup_time = 4
        self.flow = 1


class PassengerVehicleBus(ServiceVehicle):

    def __init__(self, registration: str, operator: Company):
        ServiceVehicle.__init__(self, registration=registration,  operator=operator)
        self.icao = "ZZZQ"
        self.model = "bus"
        self.model_name = "Passenger coach"
        self.setup_time = 4
        self.flow = 1


class PassengerVehicleLimousine(ServiceVehicle):

    def __init__(self, registration: str, operator: Company):
        ServiceVehicle.__init__(self, registration=registration,  operator=operator)
        self.icao = "ZZZS"
        self.model = "limousine"
        self.model_name = "VIP limousine"
        self.setup_time = 4
        self.flow = 1


# ########################
# AIRCRAFT SUPPORT
#
class AircraftVehicle(ServiceVehicle):

    def __init__(self, registration: str, operator: Company):
        ServiceVehicle.__init__(self, registration=registration,  operator=operator)
        self.icao = "ZZZA"
        self.model = ""
        self.model_name = "APU"
        self.setup_time = 4
        self.flow = 1

class AircraftVehicleAPU(ServiceVehicle):

    def __init__(self, registration: str, operator: Company):
        ServiceVehicle.__init__(self, registration=registration,  operator=operator)
        self.icao = "ZZZA"
        self.model = "apu"
        self.model_name = "APU"
        self.setup_time = 4
        self.flow = 1

class AircraftVehiclePushback(ServiceVehicle):

    def __init__(self, registration: str, operator: Company):
        ServiceVehicle.__init__(self, registration=registration,  operator=operator)
        self.icao = "ZZZP"
        self.model = "pushback"
        self.model_name = "Pushback vehicle"
        self.setup_time = 4
        self.flow = 1


# ########################
# AIPORT SUPPORT
#
class MissionVehicle(ServiceVehicle):

    def __init__(self, registration: str, operator: Company):
        ServiceVehicle.__init__(self, registration=registration,  operator=operator)
        self.icao = "ZZZR"
        self.model_name = "Mission vehicle"
        self.setup_time = 4
        self.flow = 1

    @staticmethod
    def getCombo():
        # No meta code introspection! vehicle types (and models) are manually hardcoded.
        a = []
        a.append(("security", "Security"))
        return a

class MissionVehicleSecurity(ServiceVehicle):

    def __init__(self, registration: str, operator: Company):
        ServiceVehicle.__init__(self, registration=registration,  operator=operator)
        self.icao = "ZZZR"
        self.model = "security"
        self.model_name = "Security control vehicle"
        self.setup_time = 4
        self.flow = 1

class MissionVehicleEmergency(ServiceVehicle):

    def __init__(self, registration: str, operator: Company):
        ServiceVehicle.__init__(self, registration=registration,  operator=operator)
        self.icao = "ZZZM"
        self.model = "emergency"
        self.model_name = "Emergency vehicle (ambulance)"
        self.setup_time = 4
        self.flow = 1


class MissionVehicleFire(ServiceVehicle):

    def __init__(self, registration: str, operator: Company):
        ServiceVehicle.__init__(self, registration=registration,  operator=operator)
        self.icao = "ZZZN"
        self.model = "fire"
        self.model_name = "Fire vehicle"
        self.setup_time = 4
        self.flow = 1
        # May create a few subtypes later...

