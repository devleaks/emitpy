import requests
import json

# response = requests.get("http://127.0.0.1:8000/airport/service-types")
# values = dict(response.json())
# print(values.keys())

# print("-" * 20)

# See https://github.com/tiangolo/fastapi/issues/3373
# why we need to jsonify the data
response = requests.post("http://127.0.0.1:8000/flight/", data = json.dumps({
    "airline": "QR",
    "flight_number": "195",
    "flight_date": "2022-05-07",
    "flight_time": "10:50",
    "movement": "arrival",
    "airport": "BRU",
    "ramp": "C9",
    "aircraft_type": "A35K",
    "aircraft_reg": "A7PMA",
    "call_sign": "QTR195",
    "icao24": "efface",
    "runway": "RW34L",
    "emit_rate": 30,
    "queue": "toto",
    "create_services": False
  }))

if response is not None:
    print(response)