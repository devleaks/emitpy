"""
Entities for aircraft parking on the ground.
(Currently not used. Meant to be used with the reservation/allocation system.)
"""
from typing import Union

from emitpy.business import Identity
from emitpy.constants import PASSENGER, CARGO


class AirportAOI(Identity):
    """
    A AirportAOI is an abstract base class for organizing airport buildings and areas of interest.

    """
    def __init__(self, orgId: str, classId: str, typeId: str, name: str):
        AirportAOI.__init__(self, orgId, classId, typeId, name)


class Terminal(AirportAOI):
    """
    A Terminal is a container emitpy.

    """
    def __init__(self, orgId: str, classId: str, typeId: str, name: str):
        AirportAOI.__init__(self, orgId, classId, typeId, name)
        self.concourse = {}


class Concourse(AirportAOI):
    """
    A Concourse is a container entity for passenger gates/parking.

    """
    def __init__(self, terminal: Terminal, name: str):
        AirportAOI.__init__(self, terminal.orgId, terminal.classId, "concourse", name)
        self.gates = {}


class Apron(AirportAOI):
    """
    An Apron is a container entity for parking.

    """
    def __init__(self, orgId: str, classId: str, typeId: str, name: str):
        AirportAOI.__init__(self, orgId, classId, typeId, name)
        self.parking = {}


# class Parking(AirportAOI):
#     # ugly but perfectly works.
#     pass


class Parking(AirportAOI):
    """
    A Parking uis a place to store an aircraft when it is on the ground.
    """
    def __init__(self, orgId: str, classId: str, typeId: str, name: str, size: str, shared = None):  # shared: Union[[str], [Parking]] = None
        AirportAOI.__init__(self, orgId, classId, typeId, name)
        self.usage = [CARGO, PASSENGER]  # PASSENGER or CARGO or both
        self.type = None  # {JETWAY|TIEDOWN}
        self.size = size  # A-F code
        self.gate = None  # Associated gate
        self.shared = shared    # List of overlaping parking to mark as busy when this one is busy. NB
                                # Freeing this one does not mean the other shared are free.

class Gate(AirportAOI):
    """
    This class describes a gate.
    """
    def __init__(self, orgId: str, classId: str, typeId: str, name: str):
        AirportAOI.__init__(self, orgId, classId, typeId, name)
        self.parking = None     # Associated parking if type jetway
        self.gate_type = None   # Jetway, walk, bus
