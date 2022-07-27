# Creates CZML flight path for visualisation in Cesium
from geojson import Feature


def toCZML(path: [Feature]):
    czml = ""
    for f in path:
        # -117.184650,34.627964,980
        if f["geometry"]["type"] == "Point" and len(f["geometry"]["coordinates"]) > 2:
            c = f["geometry"]["coordinates"]
            czml = czml + f"{c[0]},{c[1]},{round(c[2], 3)}\n"
    return czml