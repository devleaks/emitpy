import requests
import sys

BASE_URL="http://127.0.0.1:8000"

response = requests.get(BASE_URL + "/airport/runways", headers = {'api-key': sys.argv[1]})
print(response.json())