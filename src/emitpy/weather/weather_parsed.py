"""
Weather situation at a named location, usually an airport.
"""
import os
import logging
from datetime import datetime, timedelta, timezone

from .weather import Weather

# Choose your METAR parser here
from avwx import Metar, Taf

logger = logging.getLogger("WeatherParsed")



class WeatherFromMetar(Weather):
    """
    """
    def __init__(self, icao: str, movement_datetime: datetime = datetime.now().astimezone(), redis = None):

        Weather.__init__(self, icao=icao, movement_datetime=movement_datetime, redis=redis)


    def parse(self):
        """
        Clear protected parsing of Metar.
        If parsing succeeded, result is kept
        """
        self.content_parsed = Metar.from_report(self.content_raw)
        self.content_ok = self.content_parsed.data is not None
        self.atmap_capable = self.content_ok

    def getWindDirection(self, moment: datetime = None):
        """
        Returns wind direction if any, or None if no wind or multiple directions.
        Used at Airport to determine runways in use.
        """
        if self.content_ok:
            return self.content_parsed.data.wind_direction
        return None  # means "variable"

    def getWindSpeed(self, moment: datetime = None, alt: int = None):
        """
        Returns wind speed if any.
        """
        if self.content_ok:
            return self.content_parsed.data.wind_speed
        return None

    def getPrecipitation(self, moment: datetime = None):
        """
        Returns amount of precipitations in CM of water. No difference between water, ice, snow, hail...
        Used in flights to calculate landing distance of an aircraft.
        """
        return None  # AWVX parser does not parse precipitations

    def getDetail(self):
        if self.content_ok and self.content_parsed.translations is not None:
            return ", ".join(self.content_parsed.translations)
        return None

    def getSummary(self):
        if self.content_ok:
            return self.content_parsed.raw



class WeatherFromTAF(Weather):
    """
    """
    def __init__(self, icao: str, movement_datetime: datetime = datetime.now().astimezone(), redis = None):

        Weather.__init__(self, icao=icao, movement_datetime=movement_datetime, redis=redis)


    def parse(self):
        """
        Clear protected parsing of Metar.
        If parsing succeeded, result is kept
        """
        self.content_parsed = Taf.from_report(self.content_raw)
        self.content_ok = self.content_parsed.data is not None
        self.atmap_capable = self.content_ok

    def getWindDirection(self, moment: datetime = None):
        """
        Returns wind direction if any, or None if no wind or multiple directions.
        Used at Airport to determine runways in use.
        """
        # 1. Find in Taf.TafData if moment is valid
        # 2. Find in Taf.TafData.TafLineData which ones are valid for moment
        # 3. If more than one line, return average wind dir? or the one with highest probability
        return None  # means "variable"

    def getWindSpeed(self, moment: datetime = None, alt: int = None):
        """
        Returns wind speed if any.
        """
        return None

    def getPrecipitation(self, moment: datetime = None):
        """
        Returns amount of precipitations in CM of water. No difference between water, ice, snow, hail...
        Used in flights to calculate landing distance of an aircraft.
        """
        return None  # AWVX parser does not parse precipitations

    def getDetail(self):
        if self.content_ok and self.content_parsed.translations is not None:
            return ", ".join(self.content_parsed.translations)
        return None

    def getSummary(self):
        if self.content_ok:
            return self.content_parsed.raw
