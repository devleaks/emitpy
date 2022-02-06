"""
Test API for flightplandatabase with request caching.

"""
from __future__ import annotations
import json
from geojson import FeatureCollection
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
          51.56089782714844,
          25.272640759299097
        ]
      }
    },
    {
      "type": "Feature",
      "properties": {},
      "geometry": {
        "type": "Point",
        "coordinates": [
          51.52862548828125,
          25.333786379654885
        ]
      }
    },
    {
      "type": "Feature",
      "properties": {},
      "geometry": {
        "type": "Point",
        "coordinates": [
          51.64569854736328,
          25.37784174121271
        ]
      }
    },
    {
      "type": "Feature",
      "properties": {},
      "geometry": {
        "type": "Point",
        "coordinates": [
          51.72843933105469,
          25.209911213827688
        ]
      }
    },
    {
      "type": "Feature",
      "properties": {},
      "geometry": {
        "type": "Point",
        "coordinates": [
          51.66423797607421,
          25.178534306594393
        ]
      }
    },
    {
      "type": "Feature",
      "properties": {},
      "geometry": {
        "type": "Point",
        "coordinates": [
          51.624755859375,
          25.258669159128353
        ]
      }
    }
  ]
}"""

    oldfc = json.loads(oldfc_str)
    newfc = standard_turns(oldfc["features"])

    print(FeatureCollection(features=newfc))

if __name__ == "__main__":
    main()
