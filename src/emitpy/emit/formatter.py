import json


class Formatter:

    FILE_EXTENTION = "json"

    def __init__(self, feature: "Feature"):
        self.name = "raw"
        self.feature = feature
        self.ts = feature.getAbsoluteEmissionTime()
        self.fileformat = "json"
        if "properties" in self.feature:
            self.feature["properties"]["emitpy-format"] = self.name

    def __str__(self):
        return json.dumps(self.feature)


