#
import json
from enum import Enum

from emitpy.constants import ID_SEP, ID_SEP_ALT, REDIS_DATABASE
from emitpy.utils import key_path
import emitpy


ALL_IDENTITIES = {}


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
        self.orgId   =   orgId.replace(ID_SEP, ID_SEP_ALT)
        self.classId = classId.replace(ID_SEP, ID_SEP_ALT)
        self.typeId  =  typeId.replace(ID_SEP, ID_SEP_ALT)
        self.name    = name  # name can contain :

        self.register()


    @classmethod
    def new(cls, orgId: str, classId: str, typeId: str, name: str):
        thisone = Identity.mkId(orgId=orgId, classId=classId, typeId=typeId, name=name)
        return ALL_IDENTITIES[thisone] if thisone in ALL_IDENTITIES.keys() else cls(orgId=orgId, classId=classId, typeId=typeId, name=name)

    @staticmethod
    def mkId(orgId: str, classId: str, typeId: str, name: str):
        return ID_SEP.join([orgId.replace(ID_SEP, ID_SEP_ALT),
                            classId.replace(ID_SEP, ID_SEP_ALT),
                            typeId.replace(ID_SEP, ID_SEP_ALT),
                            name])

    @staticmethod
    def split(ident: str):
        arr = ident.split(ID_SEP)
        if len(arr) < 4:
            print(f"Identity: invalid key {ident}")
        return arr[0:3] + [ID_SEP.join(arr[3:])]

    def register(self):
        thisone = self.getId()
        if thisone in ALL_IDENTITIES.keys():
            if False:
                print(f"Identity: entity {thisone} already registered")
        else:
            ALL_IDENTITIES[thisone] = self

    def getId(self):
        return Identity.mkId(orgId=self.orgId, classId=self.classId, typeId=self.typeId, name=self.name)

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
