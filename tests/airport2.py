import os
import yaml

from geojson import Point
from parameters import DATA_DIR


AIRPORT_DATABASE = "airports"


class Airport(Point):

    def __init__(self, **kwargs):
        """
        Constructs a new instance.

        :param      icao:     The icao
        :type       icao:     str
        :param      iata:     The iata
        :type       iata:     str
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
        Point.__init__(self, kwargs.lat, kwargs.lon, kwargs.alt)
        self.icao = kwargs.icao
        self.iata = kwargs.iata
        self.name = kwargs.name
        self.city = kwargs.city
        self.country = kwargs.country


    @staticmethod
    def load(name):
        """
        Loads airport definition from YAML file

        :param      name:  Airport ICAO
        :type       name:  { str }

        Returns an Airport object or None
        """
        fn = os.path.join(DATA_DIR, AIRPORT_DATABASE, name)
        file = open(fn, "r")
        a = yaml.safe_load(file)
        file.close()
        return Airport(**a)
