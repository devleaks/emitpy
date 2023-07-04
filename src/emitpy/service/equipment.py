"""
A Service Vehicle is a vehicle used to perform a service or maintenance operation.
It has a Service Vehicle Type that is ued to represent it.
"""
import logging
import importlib, inspect
from math import inf
import re

from emitpy.business import Identity, Company
from emitpy.constants import SERVICE, DEFAULT_VEHICLE, DEFAULT_VEHICLE_SHORT

logger = logging.getLogger("Equipment")

#####################################
# SERVICE VEHICLE TYPES AND MODELS
#
#
class Equipment(Identity):
    """
    A Service Vehicle Type is a type of vehicle used to perform a service or maintenance operation.

    """
    def __init__(self, registration: str, operator: Company):
        Identity.__init__(self, operator.name, "GSE", type(self).__name__, registration)

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

        self.setup_time = 0  # unsetup time is the same
        self.flow = 1        # quantity per minute to load, unload, symmetric time


    @staticmethod
    def getCombo():
        """
        Returns (display_name, internal_name) tuple for all vehicle types.
        """
        a = []
        for name, cls in inspect.getmembers(importlib.import_module(name=".service.equipment", package="emitpy"), inspect.isclass):
            if name.__contains__("Vehicle"):
                a.append((name, name))
        return a

    @staticmethod
    def getModels(service: str = "catering"):
        """
        Returns (display_name, internal_name) tuple for each possible vehicle models for supplied service type.

        :param      service:  The service
        :type       service:  str
        """
        def toSnake(s):
            return ''.join(['_'+i.lower() if i.isupper() else i for i in s]).lstrip('_')

        def toCamel(s):
            return ''.join(map(str.title, s.split('_')))

        a = []
        base = service[0].upper() + service[1:].lower() + "Vehicle"
        for name, cls in inspect.getmembers(importlib.import_module(name=".service.equipment", package="emitpy"), inspect.isclass):
            if name.startswith(base):
                model = name.replace(base, "")
                if len(model) > 0:
                    model = toSnake(model)
                else:
                    model = "default"
                a.append((model, name))
        return a

    @staticmethod
    def new(service: str, registration: str, operator, model: str = None):
        def is_default_model(model):
            if model is None:
                return True
            return len(model) <= len(DEFAULT_VEHICLE) or model[:-len(DEFAULT_VEHICLE)] != DEFAULT_VEHICLE

        servicevehicleclasses = importlib.import_module(name=".service.equipment", package="emitpy")
        vtype = service[0].upper() + service[1:].lower() + "Vehicle"

        if not is_default_model(model):
            model = model.replace("-", "_")  # now model is snake_case
            vtype = vtype + ''.join(word.title() for word in model.split('_'))  # now model is CamelCase
            logger.debug(f"Equipment::new creating {vtype}")
            if hasattr(servicevehicleclasses, vtype):
                logger.debug(f"Equipment::new creating {vtype}")
                return getattr(servicevehicleclasses, vtype)(registration=registration, operator=operator)
        return None


    def getId(self):
        return self.name  # registration

    def getResourceId(self):
        return self.getId()

    def getKey(self):
        return self.name  # registration

    def getInfo(self):
        return {
            "icao": self.icao,
            "registration": self.registration,
            "callsign": self.registration,
            "icao24": self.icao24,
            "operator": self.operator.getInfo(),
            "service": re.sub("Vehicle(.*)$", "", type(self).__name__).lower(),  # a try..., not 100% correct
#             "classname": type(self).__name__,
            "model": self.model,
            "model_name": self.model_name
        }

    def getName(self):
        return f"{self.name} ({self.icao24})"  # registration

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
            logger.debug(f"served {self.current_load:f}.")
            served = self.current_load
            self.current_load = 0
        elif self.current_load > quantity:
            self.current_load = self.current_load - quantity
            served = quantity
            logger.debug(f"served {quantity:f}. {self.current_load:f} remaning")
        else:
            served = self.current_load
            logger.warning(f"can only serve {self.current_load:f} out of {quantity:f}. {quantity - self.current_load:f} remaning to serve")
            self.current_load = 0

        return served


# ########################
# FUEL
#
class FuelVehicle(Equipment):

    def __init__(self, registration: str, operator: Company):
        Equipment.__init__(self, registration=registration,  operator=operator)

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
        self.model_name = "Fuel pump vehicle"
        self.max_capacity = inf
        self.flow = 2.0 / 60
        self.speeds = {
            "slow": 5,
            "normal": 30,
            "fast": 60
        }
        self.setup_time = 5 * 60    # in seconds

class FuelVehicleHydrant(FuelVehicle):

    def __init__(self, registration: str, operator: Company):
        FuelVehicle.__init__(self, registration=registration,  operator=operator)
        self.icao = "ZZZF"
        self.model = "hydrant"
        self.model_name = "Fuel hydrant vehicle"
        self.max_capacity = inf
        self.flow = 2.0 / 60
        self.speeds = {
            "slow": 5,
            "normal": 30,
            "fast": 60
        }
        self.setup_time = 5 * 60    # in seconds

class FuelVehicleLargeTanker(FuelVehicle):

    def __init__(self, registration: str, operator: Company):
        FuelVehicle.__init__(self, registration=registration,  operator=operator)
        self.icao = "ZZZG"
        self.model = "large-tanker"
        self.model_name = "Fuel tanker large"
        self.max_capacity = 40
        self.flow = 1.5 / 60
        self.speeds = {
            "slow": 5,
            "normal": 20,
            "fast": 40
        }
        self.setup_time = 5 * 60    # in seconds

class FuelVehicleMediumTanker(FuelVehicle):

    def __init__(self, registration: str, operator: Company):
        FuelVehicle.__init__(self, registration=registration,  operator=operator)
        self.icao = "ZZZE"
        self.model = "medium-tanker"
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
class CateringVehicle(Equipment):

    def __init__(self, registration: str, operator: Company):
        Equipment.__init__(self, registration=registration,  operator=operator)
        self.icao = "ZZZH"
        self.model = ""
        self.model_name = "Catering vehicle"
        self.setup_time = 4
        self.flow = 1/20

# ########################
# CLEANING
#
class CleaningVehicle(Equipment):

    def __init__(self, registration: str, operator: Company):
        Equipment.__init__(self, registration=registration,  operator=operator)
        self.icao = "ZZZX"
        self.model = ""
        self.model_name = "Cleaning vehicle"
        self.setup_time = 4
        self.flow = 1/20

# ########################
# SEWAGE
#
class SewageVehicle(Equipment):

    def __init__(self, registration: str, operator: Company):
        Equipment.__init__(self, registration=registration,  operator=operator)
        self.icao = "ZZZV"
        self.model = ""
        self.model_name = "Sewage vehicle"
        self.setup_time = 4
        self.flow = 1/20

# ########################
# WATER
#
class WaterVehicle(Equipment):

    def __init__(self, registration: str, operator: Company):
        Equipment.__init__(self, registration=registration,  operator=operator)
        self.icao = "ZZZW"
        self.model = ""
        self.model_name = "Water vehicle"
        self.setup_time = 4
        self.flow = 1/20

# ########################
# CARGO
#
class CargoVehicle(Equipment):

    def __init__(self, registration: str, operator: Company):
        Equipment.__init__(self, registration=registration,  operator=operator)
        self.icao = "ZZZU"
        self.model = ""
        self.model_name = "Cargo mover vehicle"
        self.setup_time = 4
        self.flow = 1

class CargoVehicleUld(CargoVehicle):

    def __init__(self, registration: str, operator: Company):
        CargoVehicle.__init__(self, registration=registration,  operator=operator)
        self.icao = "ZZZT"
        self.model = "uld"
        self.model_name = "Cargo ULD lift"
        self.setup_time = 4
        self.flow = 1

class CargoVehicleUldTrain(CargoVehicle):

    def __init__(self, registration: str, operator: Company):
        CargoVehicle.__init__(self, registration=registration,  operator=operator)
        self.icao = "ZZZT"
        self.model = "uld-train"
        self.model_name = "Cargo ULD train"
        self.setup_time = 4
        self.flow = 1

# ########################
# BAGGAGE
#
class BaggageVehicle(Equipment):

    def __init__(self, registration: str, operator: Company):
        Equipment.__init__(self, registration=registration,  operator=operator)
        self.icao = "ZZZB"
        self.model = ""
        self.model_name = "Baggage train"
        self.setup_time = 1
        self.flow = 10

class BaggageVehicleBelt(BaggageVehicle):

    def __init__(self, registration: str, operator: Company):
        BaggageVehicle.__init__(self, registration=registration,  operator=operator)
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
        BaggageVehicle.__init__(self, registration=registration,  operator=operator)
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

class BaggageVehicleSmallTrain(BaggageVehicle):

    def __init__(self, registration: str, operator: Company):
        BaggageVehicle.__init__(self, registration=registration,  operator=operator)
        self.icao = "ZZZI"
        self.model = "small-train"
        self.model_name = "Baggage train (small)"
        self.max_capacity = 100
        self.flow = 10 / 60
        self.speeds = {
            "slow": 3,
            "normal": 10,
            "fast": 20
        }
        self.setup_time = 0    # in seconds

class BaggageVehicleLargeTrain(BaggageVehicle):

    def __init__(self, registration: str, operator: Company):
        BaggageVehicle.__init__(self, registration=registration,  operator=operator)
        self.icao = "ZZZJ"
        self.model = "large-train"
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
class CrewVehicle(Equipment):

    def __init__(self, registration: str, operator: Company):
        Equipment.__init__(self, registration=registration,  operator=operator)
        self.icao = "ZZZK"
        self.model = ""
        self.model_name = "Crew bus"
        self.setup_time = 4
        self.flow = 1

class CrewVehicleBus(CrewVehicle):

    def __init__(self, registration: str, operator: Company):
        CrewVehicle.__init__(self, registration=registration,  operator=operator)
        self.icao = "ZZZK"
        self.model = "bus"
        self.model_name = "Crew bus"
        self.setup_time = 4
        self.flow = 1

class CrewVehicleLimousine(CrewVehicle):

    def __init__(self, registration: str, operator: Company):
        CrewVehicle.__init__(self, registration=registration,  operator=operator)
        self.icao = "ZZZL"
        self.model = "limousine"
        self.model_name = "Crew limousine"
        self.setup_time = 4
        self.flow = 1

# ########################
# PASSENGERS (VIP to Economy)
#
class PassengerVehicle(Equipment):

    def __init__(self, registration: str, operator: Company):
        Equipment.__init__(self, registration=registration,  operator=operator)
        self.icao = "ZZZQ"
        self.model = ""
        self.model_name = "Passenger coach"
        self.setup_time = 4
        self.flow = 1

class PassengerVehicleStair(PassengerVehicle):

    def __init__(self, registration: str, operator: Company):
        PassengerVehicle.__init__(self, registration=registration,  operator=operator)
        self.icao = "ZZZS"
        self.model = "bus"
        self.model_name = "Passenger coach"
        self.setup_time = 4
        self.flow = 1

class PassengerVehicleBus(PassengerVehicle):

    def __init__(self, registration: str, operator: Company):
        PassengerVehicle.__init__(self, registration=registration,  operator=operator)
        self.icao = "ZZZQ"
        self.model = "bus"
        self.model_name = "Passenger coach"
        self.setup_time = 4
        self.flow = 1

class PassengerVehicleLimousine(PassengerVehicle):

    def __init__(self, registration: str, operator: Company):
        PassengerVehicle.__init__(self, registration=registration,  operator=operator)
        self.icao = "ZZZZ"
        self.model = "limousine"
        self.model_name = "VIP limousine"
        self.setup_time = 4
        self.flow = 1

# ########################
# AIRCRAFT SUPPORT
#
class AircraftVehicle(Equipment):

    def __init__(self, registration: str, operator: Company):
        Equipment.__init__(self, registration=registration,  operator=operator)
        self.icao = "ZZZA"
        self.model = ""
        self.model_name = "APU"
        self.setup_time = 4
        self.flow = 1

class AircraftVehicleApu(AircraftVehicle):

    def __init__(self, registration: str, operator: Company):
        AircraftVehicle.__init__(self, registration=registration,  operator=operator)
        self.icao = "ZZZA"
        self.model = "apu"
        self.model_name = "APU"
        self.setup_time = 4
        self.flow = 1

class AircraftVehicleAsu(AircraftVehicle):

    def __init__(self, registration: str, operator: Company):
        AircraftVehicle.__init__(self, registration=registration,  operator=operator)
        self.icao = "ZZZA"
        self.model = "asu"
        self.model_name = "ASU"
        self.setup_time = 4
        self.flow = 1

class AircraftVehiclePushback(AircraftVehicle):

    def __init__(self, registration: str, operator: Company):
        AircraftVehicle.__init__(self, registration=registration,  operator=operator)
        self.icao = "ZZZP"
        self.model = "pushback"
        self.model_name = "Pushback vehicle"
        self.setup_time = 4
        self.flow = 1

class AircraftVehicleTow(AircraftVehicle):

    def __init__(self, registration: str, operator: Company):
        AircraftVehicle.__init__(self, registration=registration,  operator=operator)
        self.icao = "ZZZT"
        self.model = "tow"
        self.model_name = "Tow vehicle"
        self.setup_time = 5
        self.flow = 1

class AircraftVehicleMarshall(AircraftVehicle):

    def __init__(self, registration: str, operator: Company):
        AircraftVehicle.__init__(self, registration=registration,  operator=operator)
        self.icao = "ZZZC"
        self.model = "marshall"
        self.model_name = "Marshall vehicle"
        self.setup_time = 4
        self.flow = 1

# ########################
# MISSIONS
#
class MissionVehicle(Equipment):

    def __init__(self, registration: str, operator: Company):
        Equipment.__init__(self, registration=registration,  operator=operator)
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

class MissionVehiclePolice(MissionVehicle):

    def __init__(self, registration: str, operator: Company):
        MissionVehicle.__init__(self, registration=registration,  operator=operator)
        self.icao = "ZZZY"
        self.model = "police"
        self.model_name = "Police vehicle"
        self.setup_time = 4
        self.flow = 1

class MissionVehicleSecurity(MissionVehicle):

    def __init__(self, registration: str, operator: Company):
        MissionVehicle.__init__(self, registration=registration,  operator=operator)
        self.icao = "ZZZR"
        self.model = "security"
        self.model_name = "Security control vehicle"
        self.setup_time = 4
        self.flow = 1

class MissionVehicleEmergency(MissionVehicle):

    def __init__(self, registration: str, operator: Company):
        MissionVehicle.__init__(self, registration=registration,  operator=operator)
        self.icao = "ZZZM"
        self.model = "emergency"
        self.model_name = "Emergency vehicle (ambulance)"
        self.setup_time = 4
        self.flow = 1

class MissionVehicleFire(MissionVehicle):

    def __init__(self, registration: str, operator: Company):
        MissionVehicle.__init__(self, registration=registration,  operator=operator)
        self.icao = "ZZZN"
        self.model = "fire"
        self.model_name = "Fire vehicle"
        self.setup_time = 4
        self.flow = 1
        # May create a few subtypes later...

