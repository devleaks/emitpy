"""
Deals with METAR data in simulation.
"""
import os
import json
import logging
import requests_cache
from datetime import datetime, timedelta

from metar import Metar as MetarLib

import flightplandb as fpdb

# from metar import Metar as MetarLib

from ..constants import METAR_DATABASE
from ..parameters import AODB_DIR

from ..private import FLIGHT_PLAN_DATABASE_APIKEY

METAR_DIR = os.path.join(AODB_DIR, METAR_DATABASE)

logger = logging.getLogger("Metar")


class Metar:
    """
    Loads cached METAR for ICAO or fetch **current** from flightplandatabase.
    """
    def __init__(self, icao: str):
        self.icao = icao
        self.raw = None
        self.metar = None
        self.api = fpdb.FlightPlanDB(FLIGHT_PLAN_DATABASE_APIKEY)

        # For development
        requests_cache.install_cache()

        self.init()


    def init(self):
        self.load()
        if self.raw is None:
            self.fetch()
            self.save()


    def fetch(self):
        metar = self.api.weather.fetch(icao=self.icao)
        if metar is not None and metar.METAR is not None:
            self.raw = metar
            if self.raw is not None:
                self.metar = MetarLib.Metar(self.raw.METAR)


    def save(self):
        if self.raw is not None:
            metid = self.raw.METAR[0:4] + '-' + self.raw.METAR[5:12]
            fn = os.path.join(METAR_DIR, metid + ".json")
            if not os.path.exists(fn):
                with open(fn, "w") as outfile:
                    json.dump(self.raw._to_api_dict(), outfile)

        logger.debug(":save: %s, %s" % (metid, fn))


    def load(self):
        def round_dt(dt, delta):  # rounds date to delta after date.
            return dt + (datetime.min - dt) % delta

        now = datetime.utcnow()
        now2 = round_dt(now - timedelta(minutes=120), timedelta(minutes=60))
        nowstr = now2.strftime('%d%H%MZ')
        fn = os.path.join(METAR_DIR, self.icao + "-" + nowstr + ".json")
        if os.path.exists(fn):
            with open(fn, "r") as fp:
                self.raw = json.load(fp)
            if self.raw is not None:
                self.metar = MetarLib.Metar(self.raw["METAR"])
            logger.debug(":load: found %s" % (fn))
        else:
            logger.debug(":load: not found %s" % (fn))

    def get(self):
        return None if self.raw is None else self.raw["METAR"]


    def parse(self):
        if self.metar is None:
            return None
