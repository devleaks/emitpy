import sys
sys.path.append('..')

import logging
from geojson import Feature, Point

from emitpy.airspace import XPAirspace
from emitpy.graph import Route

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("Airspace")

def main():

    a = XPAirspace(load_airways=True)
    logger.debug("loading..")
    a.load()
    logger.debug("..done")

    dep = a.getAirportICAO("OTHH")
    arr = a.getAirportICAO("EFHK")

    s = a.nearest_vertex(point=dep, with_connection=True)
    print(s[0].id)
    # s1 = a.nearest_point_on_edge(point=dep, with_connection=True)
    # if s1[0]:
    #     print(s[0]["id"], "[ " + s1[2].start["id"] + " -> " + s1[2].end["id"] + " ]")
    # else:
    #     print("no dep")

    e = a.nearest_vertex(point=arr, with_connection=True)
    print(e[0].id)
    # e1 = a.nearest_point_on_edge(point=arr, with_connection=True)
    # if e1[0]:
    #     print(e[0]["id"], "[ " + e1[2].start["id"] + " -> " + e1[2].end["id"] + " ]")
    # else:
    #     print("no arr")

    if s[0] is not None and e[0] is not None:
        r = Route(a, s[0].id, e[0].id)
        print(r)

main()