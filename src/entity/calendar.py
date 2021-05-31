"""
Manage reservation calendar for resources.
A Resource can be a runway, a parking, or a service vehicle.
It could even be a plane, etc.
The Calendar is meant to be associated with the resource it protects.
"""

# Reservation status. For internal use.
from datetime import date, datetime, time, timedelta
import logging

logger = logging.getLogger("Calendar")

from .info import Info

CONFIRMED = 0
PROVISIONED = 1


class Reservation(Info):
    """
    Reservation for a given duration
    """

    def __init__(self, resource: str, startime: str, endtime: str, status: int = PROVISIONED):
        Info.__init__(self)
        self.resource = resource
        self.starttime = startime
        self.endtime = endtime
        self.status = status

        def duration(self) -> int:
            """
            Returns event duration in seconds
            """
            diff = self.endtime - self.startime  # timedelta
            return diff.seconds

        def confirm(self):
            self.status = CONFIRMED



class Calendar:
    def __init__(self):
        self.slotsize = None
        pass


class SlotCalendar:
    """
    A SlotCalendar contains time reservations for a resource in a slotted calendar.
    Slot size must be supplied in seconds.
    """

    def __init__(self, slot: int):
        self.slotsize = slot  # in minutes
        self.numslots = int(24 * 60 * 60 / slot)  # per day
        self.reservations = {}  # key is day_of_year(int), then key is slot number(int), value is a Reservation
        # self.reservations = {
        #   day_of_year: {
        #       slot_number: Reservation(...)
        #   }
        # }


    def day_of_year(self, moment: datetime):
        """
        Utility function that returns the day number in year

        :param      moment:  The moment
        :type       moment:  datetime

        :returns:   { description_of_the_return_value }
        :rtype:     { return_type_description }
        """
        return moment.now().timetuple().tm_yday


    def slot_number(self, moment: datetime):
        """
        Returns slot number from calendar partition

        :param      moment:  The moment
        :type       moment:  datatime
        """
        return int((moment - moment.replace(hour=0, minute=0, second=0, microsecond=0)).total_seconds() / self.slotsize)


    def get_slot_time(self, moment: datetime, slot: int):
        """
        Returns slot datetime

        :param      moment:  The moment
        :type       moment:  datetime
        :param      slot:    The slot
        :type       slot:    int

        :returns:   The slot time.
        :rtype:     { return_type_description }
        """
        return moment.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(seconds=slot * self.slotsize)


    def get_available_slots(self, moment: datetime):
        """
        Returns array of slot numbers available for this hour

        :param      moment:  The moment
        :type       moment:  datetime

        :returns:   The available slots.
        :rtype:     { return_type_description }
        """
        hours = moment.replace(minute=0, second=0, microsecond=0)
        slot = self.slot_number(hours)
        slotperhour = int(3600 / self.slotsize)

        doy = self.day_of_year(moment)
        available = []

        if doy in self.reservations:
            currday = self.reservations[doy]
            for i in range(slot, slot + slotperhour):
                if i not in currday:
                    available.append(i)
                # else:
                #     logger.debug("get_available_slots: busy: %d, %d", doy, i)
        else:  # no reservation for today yet, all slots available for hour
            available = list(range(slot, slot + slotperhour))

        return available


    def get_next_available_slot(self, moment: datetime):
        """
        Returns next available dayofyear and slot number

        :param      moment:  The moment
        :type       moment:  datetime

        :returns:   The available slots.
        :rtype:     { return_type_description }
        """
        doy = self.day_of_year(moment)
        slot = None

        maxslots = int(3600 / self.slotsize)
        i = self.slot_number(datetime)

        while slot is None:
            if doy in self.reservations:
                currday = self.reservations[doy]
                while i < maxslots and slot is None:
                    if i not in currday:
                        slot = i
                doy += 1  # no slot for today, try tomorrow...
                i = 0
            else:  # no reservation for today yet, all slots available for hour
                slot = i

        return (doy, slot)


    def book(self, resource: str, moment: datetime, slot: int):
        """
        Book a resource, returns a Reservation or None if booking is not available.

        :param      resource:  The resource
        :type       resource:  str
        :param      moment:    The moment
        :type       moment:    datetime
        :param      slot:      The slot
        :type       slot:      int
        """
        doy = self.day_of_year(moment)
        if doy not in self.reservations:
            self.reservations[doy] = {}

        if slot in self.reservations[doy]:
            # slot is already booked
            logger.error("book: trying to book a reserved spot %s: %s (%d)", resource, moment, slot)
            return None

        # logger.debug("book: %d, %d", doy, slot)
        st = self.get_slot_time(moment, slot)
        et = self.get_slot_time(moment, slot + 1)
        r = Reservation(resource, st, et, CONFIRMED)
        # logger.debug("book: %s: %s (%d)", resource, moment, slot)

        self.reservations[doy][slot] = r
        return r


    def get_reservation(self, moment: datetime, slot: int):
        doy = self.day_of_year(moment)
        if doy not in self.reservations:
            return None

        if slot not in self.reservations[doy]:
            return None

        return self.reservations[doy][slot]


    # def book_next_available(self, moment: datetime):
    #     """
    #     Book next available slot.
    #     DOES NOT WORK across new year.

    #     :param      moment:  The moment
    #     :type       moment:  datetime

    #     :returns:   { The reservation or None if failed to find a next available slot }
    #     :rtype:     { Reservation }
    #     """
    #     doy = self.day_of_year(moment)

    #     while doy < 365:
    #         if self.reservations[doy]:
    #             currday = self.reservations[doy]
    #         else:
    #             self.reservations[doy] = {}
    #             currday = self.reservations[doy]

    #         sn = self.slot_number(moment)
    #         while sn < self.numslots and currday[sn]:  # While slots are already filled
    #             sn += 1

    #         if sn < self.numslots:
    #             st = self.get_slot_time(moment, sn)
    #             et = self.get_slot_time(moment, sn + 1)
    #             r = Reservation(st, et, CONFIRMED)
    #             currday[sn] = r
    #             return r
    #         else:
    #             doy += 1
    #             sn = 0

    #     return None
