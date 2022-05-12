import json
import flatdict

class FormatterFlat:

    FILE_EXTENTION = "json"

    def __init__(self, feature: "Feature"):
        self.name = "raw"
        self.feature = feature
        self.ts = feature.getAbsoluteEmissionTime()
        self.fileformat = "json"

    def __str__(self):
        return json.dumps(flatdict.FlatDict(self.feature).as_dict())
