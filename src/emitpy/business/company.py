"""
A Company is a generic entity, almost abstract, for operators in the simulator.
"""
from .identity import Identity


class Company(Identity):
    """
    A Company is a generic entity, almost abstract, for operators in the simulator.
    """

    def __init__(self, orgId: str, classId: str, typeId: str, name: str):
        Identity.__init__(self, orgId=orgId, classId=classId, typeId=typeId, name=name)
