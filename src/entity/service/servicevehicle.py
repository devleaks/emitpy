"""
A Service Vehicle is a vehicle used to perform a service or maintenance operation.

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
    def __init__(self, srvType: SERVICE):

        self.service = srvType
        self.speed = {}
        self.speed["slow"] = 5
        self.speed["normal"] = 30
        self.speed["fast"] = 50
        self.mapicons = []
        self.models3d = {}

        self.capacity = 1
        self.models3d["default"] = "mister-x/ground/marshall.obj"


    def model3D(self, name: str = "default"):
        return self.models3d[name] if name in self.models3d else None


    def service_time(self, quantity: float):
        """
        Time in seconds to perform a service operation provided the supplied quantity.
        """
        return quantity


class FuelTruck(ServiceVehicleType):

    def __init__(self, model: str = "default"):
        ServiceVehicleType.__init__(self, srvType = SERVICE.FUEL)
        self.model = model
        self.mapicons.append("fuel")
        self.models3d["pump"] = "mister-x/ground/fuel/fuelpump.obj"
        self.models3d["default"] = "mister-x/ground/fuel/fueltanksm.obj"
        self.models3d["smalltank"] = "mister-x/ground/fuel/fueltanksm.obj"
        self.models3d["largetank"] = "mister-x/ground/fuel/fueltanklg.obj"


class CateringTruck(ServiceVehicleType):

    def __init__(self):
        ServiceVehicleType.__init__(self, srvType = SERVICE.CATERING)
        self.mapicons.append("fork")
        self.models3d["default"] = "mister-x/ground/catering.obj"


class ULDTruck(ServiceVehicleType):

    def __init__(self):
        ServiceVehicleType.__init__(self, srvType = SERVICE.ULD)
        self.models3d["default"] = "mister-x/ground/cargo/uldlist.obj"


#####################################
# SERVICE VEHICLE
#
#
class ServiceVehicle(Identity):

    def __init__(self, svcType: ServiceVehicleType, orgId: str, classId: str, typeId: str, name: str):
        Identity.__init__(self, orgId, classId, typeId, name)

        self.svcType = svcType
