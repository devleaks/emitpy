import logging
import json
from enum import Enum, IntEnum, Flag
from datetime import datetime, timedelta
from emitpy.constants import REDIS_DATABASE, ID_SEP
from emitpy.constants import SCHEDULED, ESTIMATED, ACTUAL, TERMINATED
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


class Reservation:
    """
    A reservation is a occupied slot in an allocation table.
    """
    def __init__(self, resource: "Resource", date_from: datetime, date_to: datetime, label: str = None):
        self.resource = resource
        self.label = label
        self.scheduled = (date_from, date_to)
        self.estimated = None
        self._actual = None
        self.status = RESERVATION_STATUS.PROVISIONED.value  # to normalize

        self.eta(date_from, date_to)

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
        if self._actual is not None:
            i[ACTUAL] = {
                START: self._actual[0].isoformat(),
                END: self._actual[1].isoformat()
            }
        return i

    def getKey(self):
        return self.getId()

    def duration(self, actual: bool = False):
        if actual:
            return self._actual[1] - self._actual[0]
        return self.estimated[1] - self.estimated[0]

    def eta(self, date_from: datetime, date_to: datetime):
        self.estimated = (date_from, date_to)

    def actual(self, date_from: datetime, date_to: datetime):
        self._actual = (date_from, date_to)

    def save(self, base: str, redis):
        redis.set(key_path(base, self.getKey()), json.dumps(self.getInfo()))


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
        self.reservations = []
        self._updated = True

    def getId(self):
        return self.name

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

    def reservations(self):
        r = []
        for u in self.reservations:
            r.append(u.getInfo())
        return r

    def save(self, redis):
        # r = self.reservations()
        # if len(r) > 0:
        #     if self.updated():
        #         redis.set(self.getKey(), json.dumps(r))
        #         logger.debug(f":save: {self.getId()} saved {len(self.reservations())} reservations")
        # self._updated = False
        if len(self.reservations) > 0 and self.updated():
            k=self.getKey()
            for u in self.reservations:
                u.save(base=k, redis=redis)
            logger.debug(f":save: {self.getId()} saved {len(self.reservations)} reservations")
        self._updated = False

    def load(self, base: str, redis):
        k=self.getKey()
        rsvs = redis.keys(k + "*")
        for r in rsvs:
            rsc = redis.get(r)
            rsc = json.loads(rsc.decode("UTF-8"))
            lbl = None
            if "label" in rsc:
                lbl = rsc["label"]
            else:
                lbl = r.decode("UTF-8").split(ID_SEP)[2]
            res = Reservation(self, datetime.fromisoformat(rsc[SCHEDULED][START]), datetime.fromisoformat(rsc[SCHEDULED][END]), label=lbl)
            if ESTIMATED in rsc:
                res.eta(datetime.fromisoformat(rsc[ESTIMATED][START]), datetime.fromisoformat(rsc[ESTIMATED][END]))
            if ACTUAL in rsc:
                res.eta(datetime.fromisoformat(rsc[ACTUAL][START]), datetime.fromisoformat(rsc[ACTUAL][END]))
            self.reservations.append(res)
        # logger.debug(f":load: {self.getId()} loaded {len(self.reservations)} reservations")

    def allocations(self, actual: bool = False):
        if actual:
            return [r._actual for r in sorted(self.reservations,key= lambda x:x.estimated[0])]
        return [(r.getId(), list(map(dt, r.estimated))) for r in sorted(self.reservations,key= lambda x:x.estimated[0])]

    def add(self, reservation: Reservation):
        self.reservations.append(reservation)
        self.update()

    def remove(self, reservation: Reservation):
        self.reservations.remove(reservation)
        self.update()

    def clean(self, limit: datetime = datetime.now()):
        """
        Removes all reservations that are terminated at the time limit

        :param      limit:  The limit
        :type       limit:  datetime
        """
        for r in list(filter(lambda x: x.estimated[1]<limit, self.reservations)):
            self.remove(r)

    def book(self, req_from: datetime, req_to: datetime, label: str = None):
        r = Reservation(self, req_from, req_to, label)
        self.add(r)
        logger.debug(f":book: booked {self.getId()} for {label}")
        return r

    def isAvailable(self, req_from: datetime, req_to: datetime):
        # logger.debug(f":isAvailable: checking for {req_from} -> {req_to} ")
        if len(self.reservations) == 0:  # no reservation yet
            logger.debug(f":isAvailable: first one ok")
            return True
        if len(self.reservations) == 1:  # if after or before only reservation, it's OK
            ok = req_to < self.reservations[0].estimated[0] or req_from > self.reservations[0].estimated[1]
            if ok:
                logger.debug(f":isAvailable: second one, no overlap")
                return True
            logger.debug(f":isAvailable: second one, overlaps")
            return False
        # we have more than one reservation, sort them by start time
        busy = sorted(self.reservations, key=lambda x: x.estimated[0])
        idx = 0
        # logger.debug(f":isAvailable: busy: {len(busy)-1}")
        while idx < len(busy) - 1:
            if idx == 0 and req_to < busy[idx].estimated[0]:  # ends before first one starts is OK
                logger.debug(f":isAvailable: before first one {dt(req_to)} < {dt(busy[idx].estimated[0])} ")
                return True
            if req_from > busy[idx].estimated[1] and req_to < busy[idx+1].estimated[0]:
                logger.debug(f":isAvailable: between {idx} and {idx+1}: {dt(req_from)} > {dt(busy[idx].estimated[1])} and {dt(req_to)} < {dt(busy[idx+1].estimated[0])}")
                return True
            if (idx+1 == len(busy)-1) and req_from > busy[idx+1].estimated[1]:
                logger.debug(f":isAvailable: after last one {dt(req_from)} > {dt(busy[idx+1].estimated[1])}")
                return True
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

        reservations = list(filter(lambda x: x.estimated[1]>req_from, self.reservations))
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

    def addNamedResource(self, resource, name):
        resource._resource = Resource(name=name, table=self)  # attach it to the resource
        self.resources[name] = resource._resource

    def add(self, resource):
        self.addNamedResource(resource, resource.getId())

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
                    ret[v.getId()] = [ [t.isoformat() for t in rz.actual]+[rz.label] for rz in v.reservations]
                else:
                    ret[v.getId()] = [ [t.isoformat() for t in rz.estimated]+[rz.label] for rz in v.reservations]
        return ret

    def save(self, redis):
        for k, r in self.resources.items():
            if r.updated():
                r.save(redis=redis)
        logger.debug(f":save: {self.getId()} saved allocations")
        return (True, "AllocationTable::save completed")


    def load(self, redis):
        k=self.getKey()
        keys = redis.keys(k + "*")
        rscs = set([a.decode("UTF-8").split(ID_SEP)[2] for a in keys])
        # logger.debug(f":load: {rscs}")
        for r in rscs:
            if r in self.resources:
                rsc = self.resources[r]
                rsc.load(base=k, redis=redis)
        logger.debug(f":load: {self.getId()} loaded allocations")
        return (True, "AllocationTable::load loaded")


