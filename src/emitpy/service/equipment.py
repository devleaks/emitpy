"""
A Service Vehicle is a vehicle used to perform a service or maintenance operation.
It has a Service Vehicle Type that is ued to represent it.
"""
import logging
import importlib, inspect
from math import inf
import re

from emitpy.business import Identity, Company
from emitpy.constants import DEFAULT_VEHICLE, DEFAULT_VEHICLE_ICAO, EQUIPMENT
from emitpy.utils import toMs

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
        self.icao = DEFAULT_VEHICLE_ICAO  # "ICAO" model name, should be ZZZC for all ground vehicle, but we use ZZZA->ZZZZ

        self.icao24 = None
        self.callsign = None

        self.model = ""
        self.label = "Generic GSE Vehicle"

        self.mesh = ["emitpy/gse/marshall.obj"]

        # Movement
        self.position = None
        self.next_position = None

        self.speed = {
            "slow": toMs(kmh=5),  # km/h to m/s
            "normal": toMs(kmh=30),
            "fast": toMs(kmh=50),
        }

        # Good handling
        self.flow = 1  # units per time, ex. 1 unit every 6 seconds= 1/6 ~= 0.1666
        self.capacity = 1
        self.current_load = 0

        self.setup_time = 0  # secs
        self.cleanup_time = 0

        self._allocations = []

    @staticmethod
    def getCombo():
        """
        Returns (display_name, internal_name) tuple for all vehicle types.
        """
        a = []
        for name, cls in inspect.getmembers(
            importlib.import_module(name=".service.equipment", package="emitpy"),
            inspect.isclass,
        ):
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
            return "".join(["_" + i.lower() if i.isupper() else i for i in s]).lstrip(
                "_"
            )

        def toCamel(s):
            return "".join(map(str.title, s.split("_")))

        a = []
        base = service[0].upper() + service[1:].lower() + "Vehicle"
        for name, cls in inspect.getmembers(
            importlib.import_module(name=".service.equipment", package="emitpy"),
            inspect.isclass,
        ):
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
            return (
                len(model) <= len(DEFAULT_VEHICLE)
                or model[: -len(DEFAULT_VEHICLE)] != DEFAULT_VEHICLE
            )

        servicevehicleclasses = importlib.import_module(
            name=".service.equipment", package="emitpy"
        )
        vtype = service[0].upper() + service[1:].lower() + "Vehicle"

        if not is_default_model(model):
            model = model.replace("-", "_")  # now model is snake_case
            vtype = vtype + "".join(
                word.title() for word in model.split("_")
            )  # now model is CamelCase
            logger.debug(f"Equipment::new creating {vtype}")
            if hasattr(servicevehicleclasses, vtype):
                logger.debug(f"Equipment::new creating {vtype}")
                return getattr(servicevehicleclasses, vtype)(
                    registration=registration, operator=operator
                )
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
            "service": re.sub(
                "Vehicle(.*)$", "", type(self).__name__
            ).lower(),  # a try..., not 100% correct
            #             "classname": type(self).__name__,
            "model": self.model,
            "model_name": self.label,
        }

    def addAllocation(self, reservation):
        self._allocations.append(reservation)

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

    def setProperties(self, props: dict):
        self.flow = props.get(EQUIPMENT.FLOW.value, 1)
        capacity = props.get(EQUIPMENT.CAPACITY.value, inf)
        if isinstance(capacity, str) and capacity[0:3].lower() == "inf":
            capacity = inf
        self.capacity = capacity
        self.setup_time = props.get(EQUIPMENT.SETUP.value, 0)
        self.cleanup_time = props.get(EQUIPMENT.CLEANUP.value, 0)

    def refill(self, quantity: float = None):
        """
        Refills truck of at most quantity and returns refill time.

        :param      quantity:  The quantity
        :type       quantity:  float
        """
        if quantity is None:
            refill_quantity = self.capacity - self.current_load
        else:
            refill_quantity = quantity

        if self.current_load + refill_quantity > self.capacity:
            self.current_load = self.capacity
            # warning exceeds
        else:
            self.current_load = self.current_load + refill_quantity

        return self.service_duration(quantity=refill_quantity, add_setup=True)

    def empty(self, quantity: float = None):
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

        return self.service_duration(quantity=empty_quantity, add_setup=True)

    def service_duration(self, quantity: float, add_setup: bool = False):
        """
        Time in seconds to deliver the service for the supplied quantity.
        """
        service_time = 0
        if self.flow != 0:
            service_time = round(abs(quantity) / self.flow, 3)
        if add_setup:
            logger.debug(f"adding setup {self.setup_time}/cleanup {self.cleanup_time}")
            return self.setup_time + service_time + self.cleanup_time
        return service_time

    def load(self, quantity: float = None):
        """
        From vehicle TO aircraft
        """
        if quantity is None:
            served = self.current_load
            self.current_load = 0  # empty
            logger.debug(f"loaded {served:f}.")
        elif self.current_load > quantity:
            self.current_load = self.current_load - quantity
            served = quantity
            logger.debug(f"loaded {quantity:f}. {self.current_load:f} in vehicle")
        else:
            served = self.current_load
            self.current_load = 0  # empty
            logger.warning(
                f"can only load {self.current_load:f} out of {quantity:f}. {(quantity - served):f} remaning to serve"
            )
        return served

    def unload(self, quantity: float = None):
        """
        From aircraft TO vehicle
        """
        if quantity is None:
            unloaded = self.capacity - self.current_load
            self.current_load = self.capacity  # full
            logger.debug(f"unloaded {unloaded:f}.")
        elif self.capacity_left() > quantity:
            self.current_load = self.current_load + quantity
            unloaded = quantity
            logger.debug(f"unloaded {quantity:f}. {self.current_load:f} in vehicle")
        else:
            unloaded = self.capacity_left()
            self.current_load = self.capacity  # full
            logger.warning(
                f"can only unload {unloaded:f} out of {quantity:f}. {(quantity - unloaded):f} remaning to serve"
            )
        return unloaded

    def has_capacity(self) -> bool:
        # logger.debug(f"{self.getId()}: {self.capacity is not None and self.capacity != inf}")
        return self.capacity is not None and self.capacity != inf

    def capacity_left(self):
        return self.capacity - self.current_load


# ########################
# FUEL
#
class FuelVehicle(Equipment):
    def __init__(self, registration: str, operator: Company):
        Equipment.__init__(self, registration=registration, operator=operator)

        self.icao = "ZZZE"
        self.model = ""
        self.label = "Generic fuel vehicle (medium size tanker)"
        self.capacity = 20
        self.flow = 0.9 / 60
        self.speeds = {"slow": 5, "normal": 20, "fast": 50}
        self.setup_time = 4 * 60  # in seconds

    def refill(self):
        if self.capacity != inf:  # untested what happens if one refills infinity
            super().refill()


class FuelVehiclePump(FuelVehicle):
    def __init__(self, registration: str, operator: Company):
        FuelVehicle.__init__(self, registration=registration, operator=operator)
        self.icao = "ZZZF"
        self.model = "pump"
        self.label = "Fuel pump vehicle"
        self.capacity = inf
        self.flow = 2.0 / 60
        self.speeds = {"slow": 5, "normal": 30, "fast": 60}
        self.setup_time = 5 * 60  # in seconds


class FuelVehicleHydrant(FuelVehicle):
    def __init__(self, registration: str, operator: Company):
        FuelVehicle.__init__(self, registration=registration, operator=operator)
        self.icao = "ZZZF"
        self.model = "hydrant"
        self.label = "Fuel hydrant vehicle"
        self.capacity = inf
        self.flow = 2.0 / 60
        self.speeds = {"slow": 5, "normal": 30, "fast": 60}
        self.setup_time = 5 * 60  # in seconds


class FuelVehicleLargeTanker(FuelVehicle):
    def __init__(self, registration: str, operator: Company):
        FuelVehicle.__init__(self, registration=registration, operator=operator)
        self.icao = "ZZZG"
        self.model = "large-tanker"
        self.label = "Fuel tanker large"
        self.capacity = 40
        self.flow = 1.5 / 60
        self.speeds = {"slow": 5, "normal": 20, "fast": 40}
        self.setup_time = 5 * 60  # in seconds


class FuelVehicleMediumTanker(FuelVehicle):
    def __init__(self, registration: str, operator: Company):
        FuelVehicle.__init__(self, registration=registration, operator=operator)
        self.icao = "ZZZE"
        self.model = "medium-tanker"
        self.label = "Fuel tanker medium"
        self.capacity = 20
        self.flow = 0.9 / 60
        self.speeds = {"slow": 5, "normal": 20, "fast": 50}
        self.setup_time = 4 * 60  # in seconds


# ########################
# CATERING
#
class CateringVehicle(Equipment):
    def __init__(self, registration: str, operator: Company):
        Equipment.__init__(self, registration=registration, operator=operator)
        self.icao = "ZZZH"
        self.model = ""
        self.label = "Catering vehicle"
        self.setup_time = 4
        self.flow = 1 / 20


# ########################
# CLEANING
#
class CleaningVehicle(Equipment):
    def __init__(self, registration: str, operator: Company):
        Equipment.__init__(self, registration=registration, operator=operator)
        self.icao = "ZZZX"
        self.model = ""
        self.label = "Cleaning vehicle"
        self.setup_time = 4
        self.flow = 1 / 20


# ########################
# SEWAGE
#
class SewageVehicle(Equipment):
    def __init__(self, registration: str, operator: Company):
        Equipment.__init__(self, registration=registration, operator=operator)
        self.icao = "ZZZV"
        self.model = ""
        self.label = "Sewage vehicle"
        self.setup_time = 4
        self.flow = 1 / 20


# ########################
# WATER
#
class WaterVehicle(Equipment):
    def __init__(self, registration: str, operator: Company):
        Equipment.__init__(self, registration=registration, operator=operator)
        self.icao = "ZZZW"
        self.model = ""
        self.label = "Water vehicle"
        self.setup_time = 4
        self.flow = 1 / 20


# ########################
# CARGO
#
class CargoVehicle(Equipment):
    def __init__(self, registration: str, operator: Company):
        Equipment.__init__(self, registration=registration, operator=operator)
        self.icao = "ZZZU"
        self.model = ""
        self.label = "Cargo mover vehicle"
        self.setup_time = 4
        self.flow = 1


class CargoVehicleUld(CargoVehicle):
    def __init__(self, registration: str, operator: Company):
        CargoVehicle.__init__(self, registration=registration, operator=operator)
        self.icao = "ZZZT"
        self.model = "uld"
        self.label = "Cargo ULD lift"
        self.setup_time = 4
        self.flow = 1


class CargoVehicleUldTrain(CargoVehicle):
    def __init__(self, registration: str, operator: Company):
        CargoVehicle.__init__(self, registration=registration, operator=operator)
        self.icao = "ZZZT"
        self.model = "uld-train"
        self.label = "Cargo ULD train"
        self.setup_time = 4
        self.flow = 1


# ########################
# BAGGAGE
#
class BaggageVehicle(Equipment):
    def __init__(self, registration: str, operator: Company):
        Equipment.__init__(self, registration=registration, operator=operator)
        self.icao = "ZZZB"
        self.model = ""
        self.label = "Baggage train"
        self.setup_time = 1
        self.flow = 10


class BaggageVehicleBelt(BaggageVehicle):
    def __init__(self, registration: str, operator: Company):
        BaggageVehicle.__init__(self, registration=registration, operator=operator)
        self.icao = "ZZZB"
        self.model = "belt"
        self.label = "Baggage belt vehicle"
        self.capacity = inf
        self.flow = 1
        self.speeds = {"slow": 5, "normal": 30, "fast": 50}
        self.setup_time = 2 * 60  # in seconds


class BaggageVehicleTrain(BaggageVehicle):
    def __init__(self, registration: str, operator: Company):
        BaggageVehicle.__init__(self, registration=registration, operator=operator)
        self.icao = "ZZZD"
        self.model = "train"
        self.label = "Baggage train"
        self.capacity = 50
        self.flow = 10 / 60
        self.speeds = {"slow": 3, "normal": 10, "fast": 20}
        self.setup_time = 0  # in seconds


class BaggageVehicleSmallTrain(BaggageVehicle):
    def __init__(self, registration: str, operator: Company):
        BaggageVehicle.__init__(self, registration=registration, operator=operator)
        self.icao = "ZZZI"
        self.model = "small-train"
        self.label = "Baggage train (small)"
        self.capacity = 100
        self.flow = 10 / 60
        self.speeds = {"slow": 3, "normal": 10, "fast": 20}
        self.setup_time = 0  # in seconds


class BaggageVehicleLargeTrain(BaggageVehicle):
    def __init__(self, registration: str, operator: Company):
        BaggageVehicle.__init__(self, registration=registration, operator=operator)
        self.icao = "ZZZJ"
        self.model = "large-train"
        self.label = "Baggage train (large)"
        self.capacity = 100
        self.flow = 10 / 60
        self.speeds = {"slow": 3, "normal": 10, "fast": 20}
        self.setup_time = 0  # in seconds


# ########################
# CREW (Cabin & Flight)
#
class CrewVehicle(Equipment):
    def __init__(self, registration: str, operator: Company):
        Equipment.__init__(self, registration=registration, operator=operator)
        self.icao = "ZZZK"
        self.model = ""
        self.label = "Crew bus"
        self.setup_time = 4
        self.flow = 1


class CrewVehicleBus(CrewVehicle):
    def __init__(self, registration: str, operator: Company):
        CrewVehicle.__init__(self, registration=registration, operator=operator)
        self.icao = "ZZZK"
        self.model = "bus"
        self.label = "Crew bus"
        self.setup_time = 4
        self.flow = 1


class CrewVehicleLimousine(CrewVehicle):
    def __init__(self, registration: str, operator: Company):
        CrewVehicle.__init__(self, registration=registration, operator=operator)
        self.icao = "ZZZL"
        self.model = "limousine"
        self.label = "Crew limousine"
        self.setup_time = 4
        self.flow = 1


# ########################
# PASSENGERS (VIP to Economy)
#
class PassengerVehicle(Equipment):
    def __init__(self, registration: str, operator: Company):
        Equipment.__init__(self, registration=registration, operator=operator)
        self.icao = "ZZZQ"
        self.model = ""
        self.label = "Passenger coach"
        self.setup_time = 4
        self.flow = 1


class PassengerVehicleStair(PassengerVehicle):
    def __init__(self, registration: str, operator: Company):
        PassengerVehicle.__init__(self, registration=registration, operator=operator)
        self.icao = "ZZZS"
        self.model = "bus"
        self.label = "Passenger coach"
        self.setup_time = 4
        self.flow = 1


class PassengerVehicleBus(PassengerVehicle):
    def __init__(self, registration: str, operator: Company):
        PassengerVehicle.__init__(self, registration=registration, operator=operator)
        self.icao = "ZZZQ"
        self.model = "bus"
        self.label = "Passenger coach"
        self.setup_time = 4
        self.flow = 1


class PassengerVehicleLimousine(PassengerVehicle):
    def __init__(self, registration: str, operator: Company):
        PassengerVehicle.__init__(self, registration=registration, operator=operator)
        self.icao = "ZZZZ"
        self.model = "limousine"
        self.label = "VIP limousine"
        self.setup_time = 4
        self.flow = 1


# ########################
# AIRCRAFT SUPPORT
#
class AircraftVehicle(Equipment):
    def __init__(self, registration: str, operator: Company):
        Equipment.__init__(self, registration=registration, operator=operator)
        self.icao = "ZZZA"
        self.model = ""
        self.label = "APU"
        self.setup_time = 4
        self.flow = 1


class AircraftVehicleApu(AircraftVehicle):
    def __init__(self, registration: str, operator: Company):
        AircraftVehicle.__init__(self, registration=registration, operator=operator)
        self.icao = "ZZZA"
        self.model = "apu"
        self.label = "APU"
        self.setup_time = 4
        self.flow = 1


class AircraftVehicleAsu(AircraftVehicle):
    def __init__(self, registration: str, operator: Company):
        AircraftVehicle.__init__(self, registration=registration, operator=operator)
        self.icao = "ZZZA"
        self.model = "asu"
        self.label = "ASU"
        self.setup_time = 4
        self.flow = 1


class AircraftVehiclePushback(AircraftVehicle):
    def __init__(self, registration: str, operator: Company):
        AircraftVehicle.__init__(self, registration=registration, operator=operator)
        self.icao = "ZZZP"
        self.model = "pushback"
        self.label = "Pushback vehicle"
        self.setup_time = 4
        self.flow = 1


class AircraftVehicleTow(AircraftVehicle):
    def __init__(self, registration: str, operator: Company):
        AircraftVehicle.__init__(self, registration=registration, operator=operator)
        self.icao = "ZZZT"
        self.model = "tow"
        self.label = "Tow vehicle"
        self.setup_time = 5
        self.flow = 1


class AircraftVehicleMarshall(AircraftVehicle):
    def __init__(self, registration: str, operator: Company):
        AircraftVehicle.__init__(self, registration=registration, operator=operator)
        self.icao = "ZZZC"
        self.model = "marshall"
        self.label = "Marshall vehicle"
        self.setup_time = 4
        self.flow = 1


# ########################
# MISSIONS
#
class MissionVehicle(Equipment):
    def __init__(self, registration: str, operator: Company):
        Equipment.__init__(self, registration=registration, operator=operator)
        self.icao = "ZZZR"
        self.label = "Mission vehicle"
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
        MissionVehicle.__init__(self, registration=registration, operator=operator)
        self.icao = "ZZZY"
        self.model = "police"
        self.label = "Police vehicle"
        self.setup_time = 4
        self.flow = 1


class MissionVehicleSecurity(MissionVehicle):
    def __init__(self, registration: str, operator: Company):
        MissionVehicle.__init__(self, registration=registration, operator=operator)
        self.icao = "ZZZR"
        self.model = "security"
        self.label = "Security control vehicle"
        self.setup_time = 4
        self.flow = 1


class MissionVehicleEmergency(MissionVehicle):
    def __init__(self, registration: str, operator: Company):
        MissionVehicle.__init__(self, registration=registration, operator=operator)
        self.icao = "ZZZM"
        self.model = "emergency"
        self.label = "Emergency vehicle (ambulance)"
        self.setup_time = 4
        self.flow = 1


class MissionVehicleFire(MissionVehicle):
    def __init__(self, registration: str, operator: Company):
        MissionVehicle.__init__(self, registration=registration, operator=operator)
        self.icao = "ZZZN"
        self.model = "fire"
        self.label = "Fire vehicle"
        self.setup_time = 4
        self.flow = 1
        # May create a few subtypes later...
