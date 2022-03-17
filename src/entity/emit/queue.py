from .format import Formatter

ADMIN_QUEUE_PREFIX="ADMIN_"

class Queue:

    def __init__(self, name: str, formatter: Formatter, file_ext: str = "csv"):
        self.name = name
        self.formatter = formatter
        self.file_ext = file_ext

    def getAdminQueue(self):
        return ADMIN_QUEUE_PREFIX + "-" + self.name