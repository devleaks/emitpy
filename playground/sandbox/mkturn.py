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
          51.5972900390625,
          25.27046750488758
        ]
      }
    },
    {
      "type": "Feature",
      "properties": {},
      "geometry": {
        "type": "Point",
        "coordinates": [
          51.58905029296875,
          25.33285545946249
        ]
      }
    },
    {
      "type": "Feature",
      "properties": {},
      "geometry": {
        "type": "Point",
        "coordinates": [
          51.6386604309082,
          25.278539396522223
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

    print(FeatureCollection(features=newfc + [Feature(geometry=LineString(coords))]))

if __name__ == "__main__":
    main()
