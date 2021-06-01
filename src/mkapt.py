import logging
from entity.airport import XPAirport
from geojson import Point, Feature

logging.basicConfig(level=logging.DEBUG)

def main():

    def hascode(f):
        if "properties" in f:
            if "type" in f["properties"]:
                return f["properties"]["type"] in ("1")
        return False

    a = XPAirport("OTHH")
    a.load()
    a.ldCIFP()
    a.ldTaxiwayNetwork()

    c4 = (25.265219797985594, 51.61400029484979)
    p = a.taxiways.nearest_vertex(Feature(geometry=Point(c4)))
    print(p)

    p = a.taxiways.nearest_point_on_edges(Feature(geometry=Point(c4)))
    print(p)

main()
