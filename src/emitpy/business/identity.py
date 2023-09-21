#
import json
from datetime import datetime, timezone
from enum import Enum

from emitpy.constants import ID_SEP, ID_SEP_ALT, REDIS_DATABASE
from emitpy.constants import FLIGHT_TIME_FORMAT

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
            print(f"Identity: invalid key {ident}")  # no logger here...
        return arr[0:3] + [ID_SEP.join(arr[3:])]

    def register(self):
        thisone = self.getId()
        if thisone in ALL_IDENTITIES.keys():
            print(f"Identity: entity {thisone} already registered")
        else:
            ALL_IDENTITIES[thisone] = self

    def getIdentity(self, asArray: bool = False):
        return self.getInfo() if asArray else Identity.mkId(orgId=self.orgId, classId=self.classId, typeId=self.typeId, name=self.name)

    def getInfo(self):
        return {
            "orgId": self.orgId,
            "classId": self.classId,
            "typeId": self.typeId,
            "name": self.name
        }

    def getId(self):
        return self.getIdentity()

    def getKey(self):
        return self.getId()

    def save(self, redis):
        """
        Saves model to cache.

        :param      redis:  The redis
        :type       redis:  { type_description }
        """
        redis.set(key_path(REDIS_DATABASE.UNKNOWN.value, self.getKey()), json.dumps(self.getInfo()))
        return (True, f"{type(self).__name__}::save: saved")


class FlightId:

    def __init__(self, airline: str, flight_number: str, scheduled: "datetime", flight: str = None):
        self.airline = airline
        self.flight_number = flight_number
        self.scheduled = scheduled
        self.remote_airport = destination

    def getId(self, use_localtime: bool = False):
        if use_localtime:
            return self.airline + self.flight_number + "-S" + self.scheduled.strftime(FLIGHT_TIME_FORMAT)
        return self.airline + self.flight_number + "-S" + self.scheduled.astimezone(tz=timezone.utc).strftime(FLIGHT_TIME_FORMAT)

    @staticmethod
    def makeId(airline: str, flight_number: str, scheduled: "datetime"):
        return airline + flight_number + "-S" + scheduled.astimezone(tz=timezone.utc).strftime(FLIGHT_TIME_FORMAT)

    @staticmethod
    def parseId(flight_id):
        """
        Parses IATA flight identifier as built by getId().
        Returns dict of parsed values.

        :param      flight_id:  The flight identifier
        :type       flight_id:  { type_description }
        """
        a = flight_id.split("-")
        scheduled_utc = datetime.strptime(a[1], "S" + FLIGHT_TIME_FORMAT)
        return {
            "airline": a[0][0:2],
            "flight_number": a[2:],
            "scheduled": scheduled_utc,
            "flight": a[0]
        }

    @classmethod
    def new(cls, flight_id: str):
        return cls(**FlightId.parse(flight_id=flight_id))
