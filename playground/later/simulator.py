from airport import Airport
from airline import Airline

class Simulator:

    def __init__(self, airport: Airport):
        self.manageairport = airport
        self.airports = {}
        self.airlines = {}


    def loadData(self):
        loadAirlines()
        loadAirports()


    def loadAirlines(self):
        for airline in self.manageairport.airlines:
            a = Airline.load(airline)
            if a is not None:
                self.airlines[airline] = a


    def loadAirports(self):
        for airline in self.airlines:
            for airport in airline.airports:
                a Airport.load(airport)
                if a is not None:
                    self.airports[airport] = a


