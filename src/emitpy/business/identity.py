#
import json
from enum import Enum

from emitpy.constants import ID_SEP, REDIS_DATABASE
from emitpy.utils import key_path
import emitpy


class IDENTIFIER(Enum):
    """
    Base class for all things identified in the system, in particular aircrafts and vehicles,
    and all reolocalized objects.
    """
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
        self.version = emitpy.__version__
        self.orgId = orgId
        self.classId = classId
        self.typeId = typeId
        self.name = name

    def getId(self):
        return self.orgId + ID_SEP + self.classId + ID_SEP + self.typeId + ID_SEP + self.name

    def getKey(self):
        return self.getId()

    def getInfo(self):
        return {
            "orgId": self.orgId,
            "classId": self.classId,
            "typeId": self.typeId,
            "name": self.name
        }

    def save(self, redis):
        """
        Saves model to cache.

        :param      redis:  The redis
        :type       redis:  { type_description }
        """
        redis.set(key_path(REDIS_DATABASE.UNKNOWN.value, self.getKey()), json.dumps(self.getInfo()))
        return (True, f"{type(self).__name__}::save: saved")
