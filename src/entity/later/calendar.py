"""
Manage reservation calendar for resources.
A Resource can be a runway, a parking, or a service vehicle.
It could even be a plane, etc.
The Calendar is meant to be associated with the resource it protects.
"""

# Reservation status. For internal use.

CONFIRMED = 0
PROVISIONED = 1
CANCELLED = 2


class Reservation:
    """
    Reservation for a given duration
    """

    def __init__(self, startime: str, endtime: str, status: int = CONFIRMED):
        self.starttime = startime
        self.endtime = endtime
        self.status = status

        def duration(self):
            """
            Returns event duration in seconds
            """
            return self.endtime - self.startime  # seconds

        def confirm(self):
            self.status = CONFIRMED

        def cancel(self):
            self.status = CANCELLED


class Calendar:
    """
    A Calendar contains time reservations for a resource.
    """

    def __init__(self, name: str, slot: int = None, datetime: str = None):
        self.name = name
        self.start = datetime
        self.slot = slot
        self.reservations = {}  # key is datetime, value is a Reservation

        if self.slot and self.start:
            self.add_slots(self.start)

    def add_slots(self, datetime: str):
        """
        Adds slots for supplied day

        :param      datetime:  The datetime
        :type       datetime:  str
        """
        pass


    def round_to_slot(self, datetime):
        """
        Rounds (the time of) a datetime to the begining of a slot.

        :param      datetime:  The datetime
        :type       datetime:  { type_description }
        """
        pass


    def next_available(self, datetime: str, duration: int = None):
        """
        Return next available time for duration. If duration is not supplied,
        and if resource usage is slotted, reserve next slot.

        :param      datetime:  The datetime
        :type       datetime:  str
        """
        if duration is None and self.slot is None:
            logger.error("next_available: no duration given")

        req_begin = datetime
        req_end = req_begin.add(duration, "seconds")
        if self.slot:
            req_begin = self.round_to_slot(datetime)
            req_end = req_begin.add(self.slot, "seconds")

        return self.find_next_available(req_begin, req_end)


    def find_next_available(self, startime: str, endtime: str, provision: bool = False):
        """
        Find next available duration and provision it.

        :param      start:  The start
        :type       start:  str
        :param      end:    The end
        :type       end:    str

        :returns:   { description_of_the_return_value }
        :rtype:     { return_type_description }
        """
        if provision:
            self.reservations[stastartimert] = Reservation(name, startime, endtime, PROVISIONED)

        return None


    def remove(self, startime: str):
        if startime in self.reservations.keys():
            self.reservations[startime] = None


    def reserve(self, name: str, startime: str, endtime: str):
        self.reservations[starttime] = Reservation(name, startime, endtime, CONFIRMED)
