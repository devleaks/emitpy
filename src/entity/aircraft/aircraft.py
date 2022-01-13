

class AircraftType:
    """
    An Identity is a group of 4 strings that univoquely designate an item in the simulator
    Organisations and names are strings that designate an OWNER and a NAME for the object for that owner.
    Example: Oranisation = "Sabena owns plane named = "OO-123".
    Class and Types are strings used to group entities with similar properties in units that are "logical" for the simulator.
    Example: Class = "aircraft", Type = "A321"
    """
    def __init__(self, orgId: str, classId: str, typeId: str, name: str):
        self.orgId = orgId
        self.classId = classId
        self.typeId = typeId
        self.name = name

class Aircraft:
    """
    An Identity is a group of 4 strings that univoquely designate an item in the simulator
    Organisations and names are strings that designate an OWNER and a NAME for the object for that owner.
    Example: Oranisation = "Sabena owns plane named = "OO-123".
    Class and Types are strings used to group entities with similar properties in units that are "logical" for the simulator.
    Example: Class = "aircraft", Type = "A321"
    """
    def __init__(self, orgId: str, classId: str, typeId: str, name: str):
        self.orgId = orgId
        self.classId = classId
        self.typeId = typeId
        self.name = name
