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
          51.571197509765625,
          25.252148528835257
        ]
      }
    },
    {
      "type": "Feature",
      "properties": {},
      "geometry": {
        "type": "Point",
        "coordinates": [
          51.5423583984375,
          25.31671837192806
        ]
      }
    },
    {
      "type": "Feature",
      "properties": {},
      "geometry": {
        "type": "Point",
        "coordinates": [
          51.546478271484375,
          25.366364073894893
        ]
      }
    },
    {
      "type": "Feature",
      "properties": {},
      "geometry": {
        "type": "Point",
        "coordinates": [
          51.659088134765625,
          25.41102777587223
        ]
      }
    },
    {
      "type": "Feature",
      "properties": {},
      "geometry": {
        "type": "Point",
        "coordinates": [
          51.87469482421874,
          24.967385120722803
        ]
      }
    },
    {
      "type": "Feature",
      "properties": {},
      "geometry": {
        "type": "Point",
        "coordinates": [
          51.32125854492187,
          24.77800680315638
        ]
      }
    },
    {
      "type": "Feature",
      "properties": {},
      "geometry": {
        "type": "Point",
        "coordinates": [
          51.42974853515625,
          24.472150437226865
        ]
      }
    },
    {
      "type": "Feature",
      "properties": {},
      "geometry": {
        "type": "Point",
        "coordinates": [
          51.87881469726562,
          24.613311858120912
        ]
      }
    },
    {
      "type": "Feature",
      "properties": {},
      "geometry": {
        "type": "Point",
        "coordinates": [
          51.667327880859375,
          25.18381613394528
        ]
      }
    },
    {
      "type": "Feature",
      "properties": {},
      "geometry": {
        "type": "Point",
        "coordinates": [
          51.61651611328125,
          25.28071250637331
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
