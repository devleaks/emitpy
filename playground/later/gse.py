from resource import Resource


class GSEType:

    def __init__(self, category: str):
        self.category = category


class GSE(Resource):

    def __init__(self, name: str, gseType: GSEType):
        self.gseType = gseType

