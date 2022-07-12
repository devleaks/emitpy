"""
Entities for aircraft parking on the ground.
(Currently not used. Meant to be used with the reservation/allocation system.)
"""
from typing import Union

from emitpy.business import Identity
from emitpy.constants import PASSENGER, CARGO


class Terminal(Identity):
    """
    A Terminal is a container emitpy.

    """
    def __init__(self, orgId: str, classId: str, typeId: str, name: str):
        Identity.__init__(self, orgId, classId, typeId, name)
        self.concourse = {}


class Concourse(Identity):
    """
    A Concourse is a container entity for passenger gates/parking.

    """
    def __init__(self, terminal: Terminal, name: str):
        Identity.__init__(self, terminal.orgId, terminal.classId, "concourse", name)
        self.aprons = {}


class Apron(Identity):
    """
    An Apron is a container entity for parking.

    """
    def __init__(self, orgId: str, classId: str, typeId: str, name: str):
        Identity.__init__(self, orgId, classId, typeId, name)
        self.parking = {}


class Parking(Identity):
    # ugly but perfectly works.
    pass


class Parking(Identity):
    """
    A Parking uis a place to store an aircraft when it is on the ground.
    """
    def __init__(self, orgId: str, classId: str, typeId: str, name: str, size: str, shared: Union[[str], [Parking]] = None):
        Identity.__init__(self, orgId, classId, typeId, name)
        self.usage = [CARGO, PASSENGER]  # PASSENGER or CARGO or both
        self.type = None  # {JETWAY|TIEDOWN}
        self.size = size  # A-F code
        self.shared = shared    # List of overlaping parking to mark as busy when this one is busy. NB
                                # Freeing this one does not mean the other shared are free.

