import os
import json
import redis
from redis.commands.json.path import Path

r = redis.StrictRedis()

fn = os.path.join("..", "..", "data", "aircraft_types", "aircraft-performances.json")
with open(fn) as data_file:
    test_data = json.load(data_file)
kdata = dict(test_data)
r.json().set('ac_types', Path.root_path(), kdata)