import json
from emitpy.constants import FEATPROP


class Formatter:
    NAME = "abc"
    FILE_EXTENSION = "json"

    def __init__(self, name: str, feature: "FeatureWithProps"):
        self.name = name
        self.feature = feature

        self.ts = feature.getAbsoluteEmissionTime()
        feature.setProp(FEATPROP.EMIT_FORMAT, self.name)

    def __str__(self):
        return json.dumps(self.feature.to_geojson())

    @staticmethod
    def getAbsoluteTime(f):
        """
        Method that returns the absolute emission time of a formatted message

        :param      f:    { parameter_description }
        :type       f:    { type_description }
        """
        return f.getProp(FEATPROP.EMIT_ABSOLUTE_TIME)


class FormatterRaw(Formatter):
    NAME = "raw"
    FILE_EXTENSION = "geojson"

    def __init__(self, feature: "FeatureWithProps"):
        Formatter.__init__(self, name=FormatterRaw.NAME, feature=feature)
