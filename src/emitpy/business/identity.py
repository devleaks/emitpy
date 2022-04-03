from enum import Enum

class IDENTIFIER(Enum):
    orgId = "orgId"
    classId = "classId"
    typeId = "typeId"
    name = "name"

class Identity:
    """
    An Identity is a group of 4 strings that univoquely designate an item in the simulator
    Organisations and names are strings that designate an OWNER and a NAME for the object for that owner.
    Example: Oranisation = "Sabena owns aircraft named = "OO-123".
    Class and Types are strings used to group entities with similar properties in units that are "logical" for the simulator.
    Example: Class = "aircraft", Type = "A321"
    """
    def __init__(self, orgId: str, classId: str, typeId: str, name: str):
        self.orgId = orgId
        self.classId = classId
        self.typeId = typeId
        self.name = name

    def getInfo(self):
        return {
            "orgId": self.orgId,
            "classId": self.classId,
            "typeId": self.typeId,
            "name": self.name
        }