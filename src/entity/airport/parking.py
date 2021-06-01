"""
Entities for aircraft parking on the ground.

"""
from ..identity import Identity
from ..constants import PAX, CARGO


class Terminal(Identity):
    """
    A Terminal is a container entity.

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
    """
    A Parking uis a place to store an airport when it is on the ground.

    """
    def __init__(self, orgId: str, classId: str, typeId: str, name: str):
        Identity.__init__(self, orgId, classId, typeId, name)
        self.usage = [CARGO, PAX]  # PAX or CARGO


    def use(self, what: str, mode: bool = None):
        if mode is None:  # Query
            return what in self.usage

        # Else: set what
        if mode and what not in self.usage:
            self.usage.append(what)
        elif mode and what in self.usage:
            self.usage.remove(what)

        return what in self.usage

    @staticmethod
    def fromGeoJSON(json):
        """
        Creates a parking entity and related objects from a GeoJSON structure (properties)

        :param      json:  The json
        :type       json:  { type_description }

        :returns:   { description_of_the_return_value }
        :rtype:     { return_type_description }
        """
        return None
