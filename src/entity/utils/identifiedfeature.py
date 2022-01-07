"""
IdentifiedFeature
"""
from geojson import Feature, Geometry
from ..identity import Identity


class IdentifiedFeature(Feature):  # Alt: FeatureWithId?
    """
    A IdentifiedFeature is a Feature with mandatory identification data.
    """

    def __init__(self, geometry: Geometry, properties: dict, identity: Identity):
        props = properties.copy()
        props["orgId"] = identity.orgId
        props["classId"] = identity.classId
        props["typeId"] = identity.typeId
        props["name"] = identity.name
        Feature.__init__(self, geometry=geometry, properties=props)


    def setIdentity(self, identity: Identity):
        self.properties["orgId"] = identity.orgId
        self.properties["classId"] = identity.classId
        self.properties["typeId"] = identity.typeId
        self.properties["name"] = identity.name
