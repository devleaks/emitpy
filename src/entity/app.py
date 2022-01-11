"""
Application container
"""


class App:
    """
    Helper class dictionary to add info to entities.
    Current classes using Info:
      - Flight

    """
    def __init__(self, icao: str):
        self.icao = icao
        self.airports = {}
        self.airlines = {}


    def loadAirports(self):
        pass

    def loadAirlines(self):
        pass

