from .dbentry import DBEntry


class FlightEntry(DBEntry):

    def __init__(self, ident: str, data):
        DBEntry.__init__(self, ident, data)

