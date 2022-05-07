import os
import json
import redis
from redis.commands.json.path import Path

r = redis.StrictRedis()

fn = os.path.join("..", "..", "data", "aircraft_types", "aircraft-types-k.json")
with open(fn) as data_file:
    test_data = json.load(data_file)

r.json().set('ac_types', Path.root_path(), test_data)