# Creates CZML flight path for visualisation in Cesium
from typing import List
from emitpy.geo.turf import Feature


def toCZML(path: List[Feature]):
    """Convert list of features to Cesium Markup Language
    Args:
        path (List[Feature]): List of Features to convert

    Returns:
        str: CZML string
    """
    czml = ""
    for f in path:
        # -117.184650,34.627964,980
        if f.geometry.type == "Point" and len(f.geometry.coordinates) > 2:
            c = f.geometry.coordinates
            czml = czml + f"{c[0]},{c[1]},{round(c[2], 3)}\n"
    return czml
