"""
A Support Vehicle is an identified vehicle to assist Carriers at Locations.

"""
from indentity import Identity


class SupportVehicle(Identity):

    def __init__(self, orgId: str, classId: str, typeId: str, name: str):
        Identity.__init__(self, orgId, classId, typeId, name)
