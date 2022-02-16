"""
A Service Vehicle is a vehicle used to perform a service or maintenance operation.
It has a Service Vehicle Type that is ued to represent it.
"""
from ..constants import SERVICE
from ..business import Identity


#####################################
# SERVICE VEHICLET TYPES
#
#
class ServiceVehicleType:
    """
    A Service Vehicle Type is a type of vehicle used to perform a service or maintenance operation.

    """
    def __init__(self, srvType: SERVICE, model: str = "default"):

        self.service = srvType
        self.speed = {}
        self.speed["slow"] = 5
        self.speed["normal"] = 30
        self.speed["fast"] = 50
        self.model = model
        self.mapicons = []
        self.models3d = {}

        self.capacity = 1
        self.models3d["default"] = "mister-x/ground/marshall.obj"
        if model in self.models3d.keys():
            self.model = model

    def setModel(self, model):
        if model in self.models3d.keys():
            self.model = model

    def model3D(self):
        return self.models3d[self.model]

    def service_time(self, quantity: float):
        """
        Time in seconds to perform a service operation provided the supplied quantity.
        """
        return quantity


class CleaningService(ServiceVehicleType):

    def __init__(self):
        ServiceVehicleType.__init__(self, srvType = SERVICE.CLEANING)


class SewageService(ServiceVehicleType):

    def __init__(self):
        ServiceVehicleType.__init__(self, srvType = SERVICE.SEWAGE)


class CateringTruck(ServiceVehicleType):

    def __init__(self):
        ServiceVehicleType.__init__(self, srvType = SERVICE.CATERING)
        self.mapicons.append("fork")
        self.models3d["default"] = "mister-x/ground/catering.obj"


class WaterService(ServiceVehicleType):

    def __init__(self):
        ServiceVehicleType.__init__(self, srvType = SERVICE.WATER)


class FuelTruck(ServiceVehicleType):

    def __init__(self, model: str = "default"):
        ServiceVehicleType.__init__(self, srvType = SERVICE.FUEL)
        self.mapicons.append("fuel")
        self.models3d["pump"] = "mister-x/ground/fuel/fuelpump.obj"
        self.models3d["default"] = "mister-x/ground/fuel/fueltanksm.obj"
        self.models3d["smalltank"] = "mister-x/ground/fuel/fueltanksm.obj"
        self.models3d["largetank"] = "mister-x/ground/fuel/fueltanklg.obj"


class ULDTruck(ServiceVehicleType):

    def __init__(self):
        ServiceVehicleType.__init__(self, srvType = SERVICE.ULD)
        self.models3d["default"] = "mister-x/ground/cargo/uldlist.obj"


class BaggageService(ServiceVehicleType):

    def __init__(self):
        ServiceVehicleType.__init__(self, srvType = SERVICE.BAGGAGE)


#####################################
# SERVICE VEHICLE
#
#
class ServiceVehicle(Identity):

    def __init__(self, svcType: ServiceVehicleType, operator: str, registration: str):
        Identity.__init__(self, operator, "GSE", type(svcType).__name__, registration)
        self.svcType = svcType

