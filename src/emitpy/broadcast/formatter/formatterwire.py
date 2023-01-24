import json
from emitpy.constants import FEATPROP


class FormatterWire:

    NAME = "wire"
    FILE_EXTENSION = "json"

    def __init__(self, message: "Message"):
        self.name = "wire"
        self.message = message
        self.ts = message.getAbsoluteEmissionTime().timestamp()

    def __str__(self):
        return str(self.message)

    @staticmethod
    def getAbsoluteTime(m):
        """
        Method that returns the absolute emission time of a message

        :param      f:    { parameter_description }
        :type       f:    { type_description }
        """
        if FEATPROP.EMIT_ABSOLUTE_TIME.value in m:
            return m[FEATPROP.EMIT_ABSOLUTE_TIME.value]
        return None
