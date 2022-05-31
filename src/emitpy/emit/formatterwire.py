import json
from emitpy.constants import FEATPROP


class FormatterWire:

    FILE_EXTENTION = "json"

    def __init__(self, message: "Message"):
        self.fileformat = "json"
        self.name = "wire"

        self.message = message
        self.ts = message.getAbsoluteEmissionTime()
        self.message["emitpy-format"] = self.name

    def __str__(self):
        return json.dumps(self.message)

    @staticmethod
    def getAbsoluteTime(m):
        """
        Method that returns the absolute emission time of a message

        :param      f:    { parameter_description }
        :type       f:    { type_description }
        """
        if FEATPROP.EMIT_ABSOLUTE_TIME.value in m:
            return self.message[FEATPROP.EMIT_ABSOLUTE_TIME.value]
        return None
