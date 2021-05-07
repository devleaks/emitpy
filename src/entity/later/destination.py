from airport import Airport
from airline import Airline

class Destination:

    def __init__(self, airport: Airport):
        self.airport = airport
        self.range = None
        self.parkings = []       # parkings

