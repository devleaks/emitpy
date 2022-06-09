import requests

BASE_URL="http://127.0.0.1:8000"
API_KEY='1b646598-10b5-45cf-8f71-beb95035b9e4'

response = requests.get(BASE_URL + "/airport/runways", headers = {'api-key': API_KEY})
print(response.json())