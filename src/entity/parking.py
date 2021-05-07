"""
A Parking uis a place to store an airport when it is on the ground.

"""
from .identity import Identity


class Apron(Identity):

    def __init__(self, orgId: str, classId: str, typeId: str, name: str):
        Identity.__init__(self, orgId, classId, typeId, name)


class Temrinal(Identity):

    def __init__(self, orgId: str, classId: str, typeId: str, name: str):
        Identity.__init__(self, orgId, classId, typeId, name)


class Parking(Identity):

    def __init__(self, orgId: str, classId: str, typeId: str, name: str):
        Identity.__init__(self, orgId, classId, typeId, name)

