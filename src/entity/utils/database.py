# Database Utility Class
#
import os
import yaml
import csv

import logging
logger = logging.getLogger("Database")

from ..parameters import DATA_DIR

class Database:
    """
    Container for a list of things accessed by keyname
    """
    def __init__(self, file: str, keyname: str):
        self._data = {}
        self.file = file
        self.keyname = keyname
        self.loaded = False

    def load():
        """
        Loads Airport's from file. Do not override airport that have been registered.
        """
        if not self.loaded:
            filename = os.path.join(DATA_DIR, self.file)
            file = open(filename, "r")
            cnt = 0

            line = file.readline()

            while line:

                cnt += 1
                if(line):
                    line = file.readline()

            file.close()
            logger.debug("Database::load:%s: %d rows added", self.file, cnt)


    @staticmethod
    def find(keyvalue: str):
        Database.load()
        if keyvalue in Database._DB.keys():
            return Database._DB[keyvalue]
        return None
