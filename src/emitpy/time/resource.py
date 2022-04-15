from datetime import datetime, timedelta
import logging

logger = logging.getLogger("Resource")


def dt(t):
    # return t  # no debug
    return round((((t+timedelta(seconds=1)) - datetime.now()).seconds) / 6)/10  # debug




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
        self.status = "reserved"  # to normalize

        self.eta(date_from, date_to)

    def getId(self):
        return self.label if self.label is not None else "reservation has no id"

    def duration(self, actual: bool = False):
        if actual:
            return self._actual[1] - self._actual[0]
        return self.estimated[1] - self.estimated[0]

    def eta(self, date_from: datetime, date_to: datetime):
        self.estimated = (date_from, date_to)

    def actual(self, date_from: datetime, date_to: datetime):
        self._actual = (date_from, date_to)


class Resource:
    """
    Array of Reservations for a Resource.
    Used to check for availability and book Reservations.
    Typical resources:
     - Vehicle (or persons)
     - Ramps
     - Runways
    """
    def __init__(self, name: str):
        self.name = name
        self.usage = []


    def getId(self):
        return self.name


    def allocations(self, actual: bool = False):
        if actual:
            return [r._actual for r in sorted(self.usage,key= lambda x:x.estimated[0])]
        return [(r.getId(), list(map(dt, r.estimated))) for r in sorted(self.usage,key= lambda x:x.estimated[0])]


    def add(self, reservation: Reservation):
        self.usage.append(reservation)


    def remove(self, reservation: Reservation):
        self.usage.remove(reservation)


    def clean(self, limit: datetime = datetime.now()):
        """
        Removes all reservations that are terminated at the time limit

        :param      limit:  The limit
        :type       limit:  datetime
        """
        for r in list(filter(lambda x: x.estimated[1]<limit, self.usage)):
            self.remove(r)


    def book(self, req_from: datetime, req_to: datetime, label: str = None):
        r =Reservation(self, req_from, req_to, label)
        self.add(r)
        return r


    def isAvailable(self, req_from: datetime, req_to: datetime):
        # logger.debug(f":isAvailable: checking for {req_from} -> {req_to} ")
        if len(self.usage) == 0:  # no reservation yet
            logger.debug(f":isAvailable: first one ok")
            return True
        if len(self.usage) == 1:  # if after or before only reservation, it's OK
            ok = req_to < self.usage[0].estimated[0] or req_from > self.usage[0].estimated[1]
            if ok:
                logger.debug(f":isAvailable: second one, no overlap")
                return True
            logger.debug(f":isAvailable: second one, overlaps")
            return False
        # we have more than one reservation, sort them by start time
        busy = sorted(self.usage, key=lambda x: x.estimated[0])
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

        reservations = list(filter(lambda x: x.estimated[1]>req_from, self.usage))
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
    def __init__(self, resources):
        self.resources = {}

        for r in resources:
            self.resources[r.getId()] = Resource(r.getId())

    def isAvailable(self, name, req_from: datetime, req_to: datetime):
        return self.resources[name].isAvailable(req_from, req_to)

    def book(self, name, req_from: datetime, req_to: datetime):
        return self.resources[name].book(req_from, req_to)

