

class Reservation:

    def __init__(self, name: str, date_from: datetime, date_to: datetime):
        self.name = name
        self.scheduled = (date_from, date_to)
        self.adjust(date_from, date_to)
        self._actual = None

    def adjust(self, name: str, date_from: datetime, date_to: datetime):
        self.estimated = (date_from, date_to)

    def actual(self, name: str, date_from: datetime, date_to: datetime):
        self._actual = (date_from, date_to)


class Resource:

    def __init__(self):
        self.name = name
        self.usage = []

    def add(self: reservation: Reservation):
        self.usage.append(reservation)

    def remove(self: reservation: Reservation):
        self.usage.remove(reservation)

    def isAvailable(self, req_from: datetime, req_to: datetime, book: bool = False):

        return False

        if book:
            self.add(Reservation(self.name, req_from, req_to))
        return True
