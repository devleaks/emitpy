"""
Dictionary for YAML file.
"""
import os
import yaml
import logging
import dpath.util

logger = logging.getLogger("Constant")

from .constants import MANAGED_AIRPORT
from .parameters import DATA_DIR


class Constant:

    def __init__(self, icao: str, name: str):
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
        filename = os.path.join(DATA_DIR, MANAGED_AIRPORT, icao, name + ".yaml")
        if os.path.isfile(filename):
            file = open(filename, "r")
            self._rawdata = yaml.safe_load(file)
            file.close()
            # logger.debug(yaml.dump(self._rawdata, indent=4))
        else:
            logger.error("init: cannot find %s", filename)
            self._rawdata = {}

    # def monoget(self, name):
    #     """
    #     Returns the value of the name constant supplied.

    #     :param      name:  The name
    #     :type       name:  { type_description }
    #     """
    #     if name in self._rawdata.keys():
    #         return self._rawdata[name]
    #     return None

    # def deepget(self, dotted_key):
    #     """
    #     Returns the value of the nested named constant. Constant's name is supplied either
    #     as a dot-separated string "a.b.c" or an array of elements ["a", "b", "c"].

    #     :param      dotted_key:  The dotted key
    #     :type       dotted_key:  { type_description }
    #     """
    #     s = dotted_key if type(dotted_key) == str else ".".join(dotted_key)

    #     return dpath.util.get(self._rawdata, s, separator=".")

    def get(self, name):
        """
        Returns the value of the named constant. Constant's name is supplied either
        as a single name, or a dot-separated string "a.b.c", or an array of elements ["a", "b", "c"].

        :param      dotted_key:  The dotted key
        :type       dotted_key:  { type_description }
        """
        s = name if type(name) == str else ".".join(name)  # else, assumed to be array/list of strings
        if len(s.split(".")) > 1:  # dotted string
            return dpath.util.get(self._rawdata, s, separator=".")
        elif s in self._rawdata.keys():
            return self._rawdata[s]
        return None
        # keys = dotted_key.split('.')
        # return functools.reduce(lambda d, key: d.get(key) if d else None, keys, self._rawdata)
