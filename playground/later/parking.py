from geojson import Point
from gse import GSEType



class ServicePosition(Point):
    """
    A service position is a position where a service vehicle is invited to stop to perform its task.
    For exemple, fuel pomp trucks locate themselves close to under wings,
    catering trucks at the "back of the place", etc.
    """

    def __init__(self, name, gseType: GSEType, sizefactor: int, lat: float, lon: float):
        Point.__init__(self, lat, lon)


class Parking(Point):  # Point, Resource

    def __init__(self, name, lat: float, lon: float, heading: float, sizecode: str):
        Point.__init__(self, (lat, lon))
        self.heading = heading
        self.sizecode = sizecode
        self.servicePositions = []


    def build(self, gseTypes: [GSEType]):
        pass