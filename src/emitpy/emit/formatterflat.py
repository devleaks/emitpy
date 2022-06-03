import json
import flatdict

class FormatterFlat:

    FILE_EXTENTION = "json"

    def __init__(self, feature: "Feature"):
        self.name = "flat"
        self.feature = feature
        self.ts = feature.getAbsoluteEmissionTime()
        self.fileformat = "json"
        if "properties" in self.feature:
            self.feature["properties"]["emitpy-format"] = self.name


    def __str__(self):
        # self.feature["properties"] = dict(flatdict.FlatDict(self.feature["properties"]))
        # return json.dumps(self.feature)
        return json.dumps(dict(flatdict.FlatDict(self.feature)))


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