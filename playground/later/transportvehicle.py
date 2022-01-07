"""
A Transport Vehicle is an identified vehicle to transport people or goods from a departure location to an arrival location.

"""
from indentity import Identity


class TransportVehicle(Identity):

    def __init__(self, orgId: str, classId: str, typeId: str, name: str):
        Identity.__init__(self, orgId, classId, typeId, name)
