import requests
import json
import sys

BASE_URL="http://127.0.0.1:8000"


response = requests.get(BASE_URL + "/auth/new",
                        headers = {'secret-key': sys.argv[1]},
                        data = json.dumps({"never_expires": True}))
print(response.json())