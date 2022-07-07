import json

from emitpy.geo import FeatureWithProps
from .formatter import FormatterBase


class Template(FormatterBase):

    """
    Mandatory, must be unique in Emitpy formatter names, used as PK.
    """
    NAME = "tmpl"

    def __init__(self, feature: FeatureWithProps):
        """
        Formatter receives a single entity, which happens to be a GeoJSON Feature<Point>
        with additional functions to easily access properties.

        :param      feature:  GeoJSON Feature<Point> for format
        :type       feature:  GeoJSON Feature<Point> with helper functions
        """
        FormatterBase.__init__(self, name="tmpl", feature=feature)


    def __str__(self):
        """
        Terminal function called for format the Feature ( str(feature) ).

        :returns:   String representation of the object.
        :rtype:     { return_type_description }
        """
        return json.dumps(self.feature)


    def helper(self):
        """
        Helper functions as needed.
        """
        return None

