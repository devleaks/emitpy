import json
from emitpy.constants import FEATPROP


class Formatter:

    NAME = "abc"

    def __init__(self, name: str, feature: "FeatureWithProps"):
        self.feature = feature
        self.name = name

        self.ts = feature.getAbsoluteEmissionTime()
        self.fileformat = "json"
        if "properties" in self.feature:
            self.feature["properties"]["emitpy-format"] = self.name

    def __str__(self):
        return json.dumps(self.feature)

    @staticmethod
    def getAbsoluteTime(f):
        """
        Method that returns the absolute emission time of a formatted message

        :param      f:    { parameter_description }
        :type       f:    { type_description }
        """
        if "properties" in f and FEATPROP.EMIT_ABSOLUTE_TIME.value in f["properties"]:
            return f["properties"][FEATPROP.EMIT_ABSOLUTE_TIME.value]
        return None


class FormatterRaw(Formatter):

    NAME = "raw"

    def __init__(self, feature: "FeatureWithProps"):
        Formatter.__init__(self, name=FormatterRaw.NAME, feature=feature)
