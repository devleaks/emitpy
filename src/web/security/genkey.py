import requests
import json

BASE_URL="http://127.0.0.1:8000"
SECRET_KEY='60a4dfdb-63a5-4481-a760-885a3a1c1474'

response = requests.get(BASE_URL + "/auth/new",
                        headers = {'secret-key': SECRET_KEY},
                        data = json.dumps({"never_expires": True}))
print(response.json())