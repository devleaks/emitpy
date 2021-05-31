"""
A location is a named geographic point (lat, lon, alt).

"""
from geojson import Point


class Location:

    def __init__(self, name: str, city: str, country: str, lat: float, lon: float, alt: float):
        """
        Create new location instance.

        :param      name:     The name
        :type       name:     str
        :param      city:     The city
        :type       city:     str
        :param      country:  The country
        :type       country:  str
        :param      lat:      The lat
        :type       lat:      float
        :param      lon:      The lon
        :type       lon:      float
        :param      alt:      The alternate
        :type       alt:      float
        """
        self.name = name
        self.city = city
        self.country = country
        if alt is not None:
            self.point = Point((lat, lon, alt))
        else:
            self.point = Point((lat, lon))
