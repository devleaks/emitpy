


class Beacon:

    def __init__(self, name, frequency=30):
        self.name = name
        self.frequency = frequency
        self.lastEmit = None


    def emitNow(self, now) -> bool:
        # Returns True/False if emited
        if self.lastEmit + self.frequency < now:
            self.emit()
            self.lastEmit = now
            return True
        return False

    def emit(self) -> None:
        return None
