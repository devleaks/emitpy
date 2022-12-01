# Resource and allocation management
import logging
from datetime import datetime, timedelta

from enum import Enum

from redis.commands.json.path import Path

from emitpy.constants import REDIS_DATABASE, ID_SEP
from emitpy.constants import SCHEDULED, ESTIMATED, ACTUAL
from emitpy.utils import key_path

logger = logging.getLogger("Resource")


def dt(t):
    return t  # no debug
    # return round((((t+timedelta(seconds=1)) - datetime.now()).seconds) / 6)/10  # debug

class RESERVATION_STATUS(Enum):
    PROVISIONED = "p"
    CONFIRMED = "c"
    COMPLETED = "d"
    CANCELLED = "e"

START = "start"
END = "end"


# Note to self: Should ensure that AllocationTable.name + Resource.name + Reservation.label is a PK.
# For now, we *suppose* it is the case.

class Reservation:
    """
    A reservation is a occupied slot in an allocation table.
    """
    def __init__(self, resource: "Resource", date_from: datetime, date_to: datetime, label: str):
        self.resource = resource
        self.label = label  # refactor to name
        self.scheduled = (date_from, date_to)
        self.estimated = None
        self.actual = None
        self.status = RESERVATION_STATUS.PROVISIONED.value  # to normalize

        self.setEstimatedTime(date_from, date_to)

    @classmethod
    def new(key):
        pass

    def getId(self):
        return self.label if self.label is not None else self.scheduled[0].isoformat()

    def getInfo(self):
        i = {
            "type": "reservation",
            "name": self.resource.getInfo(),
            SCHEDULED: {
                START: self.scheduled[0].isoformat(),
                END: self.scheduled[1].isoformat()
            },
            "label": self.label,
            "status": self.status
        }
        if self.estimated is not None:
            i[ESTIMATED] = {
                START: self.estimated[0].isoformat(),
                END: self.estimated[1].isoformat()
            }
        if self.actual is not None:
            i[ACTUAL] = {
                START: self.actual[0].isoformat(),
                END: self.actual[1].isoformat()
            }
        return i

    def getKey(self):
        return self.getId()

    def duration(self, actual: bool = False):
        if actual:
            return self.actual[1] - self.actual[0]
        return self.estimated[1] - self.estimated[0]

    def setEstimatedTime(self, date_from: datetime, date_to: datetime):
        self.estimated = (date_from, date_to)

    def setActualTime(self, date_from: datetime, date_to: datetime):
        self.actual = (date_from, date_to)

    def save(self, base: str, redis):
        redis.json().set(key_path(base, self.getKey()), Path.root_path(), self.getInfo())
        # logger.debug(f":save: {key_path(base, self.getKey())}")


class Resource:
    """
    Array of Reservations for a Resource.
    Used to check for availability and book Reservations.
    Typical resources:
     - Vehicle (or persons)
     - Ramps
     - Runways
    """
    def __init__(self, name: str, table: str):
        self.table = table
        self.name = name
        self.reservations = {}
        self._updated = True

    def getId(self):
        return self.name

    def getResourceId(self):
        return self.getId()

    def getInfo(self):
        i = {
            "type": "resource",
            "name": self.name
        }
        if self.table is not None:
            i["table"] = self.table.getId()
        return i

    def getKey(self):
        if self.table is not None:
            return key_path(self.table.getKey(), self.getId())
        return self.getId()

    def update(self):
        self._updated = True

    def updated(self):
        return self._updated

    def reservationInfos(self):
        return [r.getInfo() for r in self.reservations.values()]

    def save(self, redis):
        # r = self.reservations()
        # if len(r) > 0:
        #     if self.updated():
        #         redis.set(self.getKey(), json.dumps(r))
        #         logger.debug(f":save: {self.getId()} saved {len(self.reservations())} reservations")
        # self._updated = False
        if len(self.reservations) > 0 and self.updated():
            k=self.getKey()
            for u in self.reservations.values():
                u.save(base=k, redis=redis)
            # logger.debug(f":save: {self.getId()} saved {len(self.reservations)} reservations")
        self._updated = False

    def load(self, base: str, redis):
        k = self.getKey()
        rsvs = redis.keys(key_path(k, "*"))
        for r in rsvs:
            rsc = redis.json().get(r)
            lbl = None
            if "label" in rsc:
                lbl = rsc["label"]
            else:
                lbl = r.decode("UTF-8").split(ID_SEP)[2]
            res = Reservation(self, datetime.fromisoformat(rsc[SCHEDULED][START]), datetime.fromisoformat(rsc[SCHEDULED][END]), label=lbl)
            if ESTIMATED in rsc:
                res.setEstimatedTime(datetime.fromisoformat(rsc[ESTIMATED][START]), datetime.fromisoformat(rsc[ESTIMATED][END]))
            if ACTUAL in rsc:
                res.setEstimatedTime(datetime.fromisoformat(rsc[ACTUAL][START]), datetime.fromisoformat(rsc[ACTUAL][END]))
            self.add(res)
            # logger.debug(f":load: loaded {r.decode('UTF-8')}")
        # logger.debug(f":load: {self.getId()} loaded {len(self.reservations)} reservations")

    def allocations(self, actual: bool = False):
        if actual:
            return [r.actual for r in sorted(self.reservations.values(),key= lambda x:x.estimated[0])]
        return [(r.getId(), list(map(dt, r.estimated))) for r in sorted(self.reservations.values(),key= lambda x:x.estimated[0])]

    def add(self, reservation: Reservation):
        if reservation.label in self.reservations.keys():
            logger.warning(f":add: {reservation.label} already exists, overwriting")
        self.reservations[reservation.label] = reservation
        self.update()

    def remove(self, reservation: Reservation):
        if reservation.label in self.reservations.keys():
            del self.reservations[reservation.label]
        self.update()

    def clean(self, limit: datetime = datetime.now()):
        """
        Removes all reservations that are terminated at the time limit

        :param      limit:  The limit
        :type       limit:  datetime
        """
        for r in list(filter(lambda x: x.estimated[1]<limit, self.reservations.values())):
            self.remove(r)

    def book(self, req_from: datetime, req_to: datetime, label: str = None):
        r = Reservation(self, req_from, req_to, label)
        self.add(r)
        logger.debug(f":book: booked {self.getId()} for {label}, {req_from} to {req_to}")
        return r

    def isAvailable(self, req_from: datetime, req_to: datetime):
        # logger.debug(f":isAvailable: checking for {req_from} -> {req_to} ")
        resarr = list(self.reservations.values())

        if len(resarr) == 0:  # no reservation yet
            logger.debug(f":isAvailable: first one ok")
            return True
        if len(resarr) == 1:  # if after or before only reservation, it's OK
            ok = req_to < resarr[0].estimated[0] or req_from > resarr[0].estimated[1]
            if ok:
                logger.debug(f":isAvailable: second one, no overlap")
                return True
            logger.debug(f":isAvailable: second one, overlaps")
            return False
        # we have more than one reservation, sort them by start time
        busy = sorted(resarr, key=lambda x: x.estimated[0])
        idx = 0
        # logger.debug(f":isAvailable: busy: {len(busy)-1}")
        while idx < len(busy) - 1:
            try:
                if idx == 0 and req_to < busy[idx].estimated[0]:  # ends before first one starts is OK
                    logger.debug(f":isAvailable: before first one {dt(req_to)} < {dt(busy[idx].estimated[0])} ")
                    return True
                if req_from > busy[idx].estimated[1] and req_to < busy[idx+1].estimated[0]:
                    logger.debug(f":isAvailable: between {idx} and {idx+1}: {dt(req_from)} > {dt(busy[idx].estimated[1])} and {dt(req_to)} < {dt(busy[idx+1].estimated[0])}")
                    return True
                if (idx+1 == len(busy)-1) and req_from > busy[idx+1].estimated[1]:
                    logger.debug(f":isAvailable: after last one {dt(req_from)} > {dt(busy[idx+1].estimated[1])}")
                    return True
            except:
                logger.warning(f":is_available: issue at {busy[idx].label}")
            idx = idx + 1
        return False


    def firstAvailable(self, req_from: datetime, req_to: datetime):
        """
        Finds first availability where requested usage can be inserted after req_from.
        (milliseconds added to time to avoid rounding issues and <= or >= of time with resolution)

        :param      req_from:  The request from
        :type       req_from:  datetime
        :param      req_to:    The request to
        :type       req_to:    datetime

        :returns:   { description_of_the_return_value }
        :rtype:     { return_type_description }
        """
        if self.isAvailable(req_from, req_to):
            return (req_from, req_to)

        duration = req_to - req_from

        resarr = list(self.reservations.values())
        reservations = list(filter(lambda x: x.estimated[1]>req_from, resarr))
        logger.debug(f":firstAvailable: {len(reservations)} reservations ends after {dt(req_from)}")
        if len(reservations) == 0:
            logger.debug(":firstAvailable: available as requested")
            return (req_from, req_to)
        if len(reservations) == 1:  # only one reservation that starts after req_from, probably overlaps
            soonest = reservations[0].estimated[1] + timedelta(milliseconds=1)
            logger.debug(f":firstAvailable: added after last reservation {dt(soonest)}")
            return (soonest, soonest + duration)
        busy = sorted(reservations, key=lambda x: x.estimated[0])
        # Can we insert it between 2 usages?
        for idx in range(len(busy)-1):
            squeeze = busy[idx+1].estimated[0] - busy[idx].estimated[1] + timedelta(milliseconds=2)
            if squeeze > duration:  # we can fit it
                soonest = busy[idx].estimated[1] + timedelta(milliseconds=1)
                logger.debug(f":firstAvailable: squeezed at {idx}, added after {dt(soonest)}")
                return (soonest, soonest + duration)
        # no, so add it at the end
        soonest = busy[-1].estimated[1] + timedelta(milliseconds=1)
        logger.debug(f":firstAvailable: cannot squeeze, added after last reservation {dt(soonest)}")
        return (soonest, soonest + duration)


    def findReservation(self, label: str):
        if label in self.reservations:
            return self.reservations[label]
        logger.debug(f":findReservation: {self.name}: reservation {label} not found")
        logger.debug(self.reservations.keys())
        return None


class AllocationTable:
    """
    An allocation table is a collection of resources and usage.
    """
    def __init__(self, resources, name: str):
        self.name = name
        self.resources = {}
        for r in resources:
            self.add(r)

    def getId(self):
        return self.name

    def getInfo(self):
        return {
            "type": "allocation-table",
            "name": self.name
        }

    def getKey(self):
        return key_path(REDIS_DATABASE.ALLOCATIONS.value, self.getId())

    def addResource(self, name: str, resource: "Resource"):
        if name in self.resources.keys():
            logger.warning(f":add: {name} already exists, overwriting")
        self.resources[name] = resource

    def createNamedResource(self, resource, name):
        resource._resource = Resource(name=name, table=self)
        self.addResource(name, resource._resource)

    def add(self, resource):
        """
        The object added must have a getResourceId() method.

        :param      resource:  The resource
        :type       resource:  { type_description }
        """
        self.createNamedResource(resource, resource.getResourceId())

    def isAvailable(self, name, req_from: datetime, req_to: datetime):
        """
        Checks whether a reservation overlap with another for the supplied resource identifier.

        :param      name:      The name
        :type       name:      { type_description }
        :param      req_from:  The request from
        :type       req_from:  datetime
        :param      req_to:    The request to
        :type       req_to:    datetime

        :returns:   True if available, False otherwise.
        :rtype:     bool
        """
        return self.resources[name].isAvailable(req_from, req_to)

    def book(self, name, req_from: datetime, req_to: datetime, reason: str):
        """
        Book a reservation, even if it overlaps with other reservation.
        Returns the reservation.

        :param      name:      The name
        :type       name:      { type_description }
        :param      req_from:  The request from
        :type       req_from:  datetime
        :param      req_to:    The request to
        :type       req_to:    datetime
        :param      reason:    The reason
        :type       reason:    str

        :returns:   { description_of_the_return_value }
        :rtype:     { return_type_description }
        """
        return self.resources[name].book(req_from, req_to, label=reason)

    def table(self, actual: bool = False):
        """
        Returns a dictionary of all resources and their reservations.
        """
        ret = {}
        for r, v in self.resources.items():
            if len(v.reservations) > 0:
                if actual:
                    ret[v.getId()] = [ [t.isoformat() for t in rz.actual]+[rz.label] for rz in v.reservations.values()]
                else:
                    ret[v.getId()] = [ [t.isoformat() for t in rz.estimated]+[rz.label] for rz in v.reservations.values()]
        return ret

    def save(self, redis):
        for k, r in self.resources.items():
            if r.updated():
                r.save(redis=redis)
        # logger.info(f":AT:save: {self.getId()} saved resources")
        return (True, "AllocationTable::save completed")

    def load(self, redis):
        if redis is None:
            return (True, "AllocationTable::load: no Redis")

        keys = redis.keys(key_path(self.getKey() , "*"))
        rscs = set([a.decode("UTF-8").split(ID_SEP)[2] for a in keys])
        for r in rscs:
            if r not in self.resources:
                rsc = Resource(name=r, table=self)
                self.addResource(name=r, resource=rsc)
            else:
                rsc = self.resources[r]
            rsc.load(base=self.getId(), redis=redis)
        logger.debug(f":AT:load: {self.getId()} loaded {len(rscs)} resources")
        return (True, "AllocationTable::load loaded")

    def findReservation(self, resource: str, label: str, redis = None) -> Reservation:
        if resource in self.resources.keys():
            rsc = self.resources[resource]
            return rsc.findReservation(label)
        logger.debug(f":AT:findReservation: {self.name}: resource {resource} not found")
        if redis:
            k = key_path(self.getKey(), resource, label)
            logger.debug(f":AT:findReservation: {k}")
            if k is not None:
                self.resources[resource] = Resource(name=resource, table=self)
                self.resources[resource].load(base=self.getId(), redis=redis)
                return self.resources[resource].findReservation(label)
        logger.debug(f":AT:findReservation: {self.name}: resource {resource} not found in Redis")
        return None
