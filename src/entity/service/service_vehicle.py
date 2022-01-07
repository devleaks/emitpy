"""
A Service Vehicle is a vehicle used to perform a service or maintenance operation.

"""
from ..identity import Identity
from .service_vehicle_type import ServiceVehicleType


class ServiceVehicle(ServiceVehicleType, Identity):

    def __init__(self, srvType: str, orgId: str, classId: str, typeId: str, name: str):
        Identity.__init__(self, orgId, classId, typeId, name)
        ServiceVehicleType.__init__(self, srvType)
