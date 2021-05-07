"""
Dictionary for YAML file.
"""
import os
import yaml
import logging
import functools
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

    def get(self, name):
        if name in self._rawdata.keys():
            return self._rawdata[name]
        return None

    def deepget(self, dotted_key):
        s = dotted_key if type(dotted_key) == str else ".".join(dotted_key)

        return dpath.util.get(self._rawdata, s, separator=".")
        # keys = dotted_key.split('.')
        # return functools.reduce(lambda d, key: d.get(key) if d else None, keys, self._rawdata)
