import json
import flatdict
from .formatter import FormatterBase


class FormatterFlat(FormatterBase):

    NAME = "flat"

    def __init__(self, feature: "Feature"):
        FormatterBase.__init__(self, name=FormatterFlat.NAME, feature=feature)


    def __str__(self):
        # self.feature["properties"] = dict(flatdict.FlatDict(self.feature["properties"]))
        # return json.dumps(self.feature)
        return json.dumps(dict(flatdict.FlatDict(self.feature)))
