"""
Test API for flightplandatabase with request caching.

"""
from __future__ import annotations
import json
from geojson import FeatureCollection, LineString, Feature
from standardturn import standard_turns

def main():

    oldfc_str = """{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "properties": {},
      "geometry": {
        "type": "Point",
        "coordinates": [
          51.63471221923828,
          25.17449510769419
        ]
      }
    },
    {
      "type": "Feature",
      "properties": {},
      "geometry": {
        "type": "Point",
        "coordinates": [
          51.616859436035156,
          25.31795976270813
        ]
      }
    },
    {
      "type": "Feature",
      "properties": {},
      "geometry": {
        "type": "Point",
        "coordinates": [
          51.690673828125,
          25.36853560809667
        ]
      }
    }
  ]
}"""


    oldfc = json.loads(oldfc_str)

    coords = []
    for x in oldfc["features"]:
        coords.append(x["geometry"]["coordinates"])


    newfc = standard_turns(oldfc["features"])

#    print(FeatureCollection(features=newfc + [Feature(geometry=LineString(coords))]))

if __name__ == "__main__":
    main()
