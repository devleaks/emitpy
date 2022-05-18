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
        return json.dumps(flatdict.FlatDict(self.feature).as_dict())
