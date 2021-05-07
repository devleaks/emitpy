
from .calendar import SlotCalendar, Calendar



class Resource:

    def __init__(self, name: str, slot: int = None):
        self.name = name
        self.calendar = SlotCalendar(slot) if slot else Calendar()
