import os
import sys
import json
import redis
from redis.commands.json.path import Path

r = redis.StrictRedis()

kn = sys.argv[1]
fn = sys.argv[2]  # os.path.join("..", "..", "data", "aircraft_types", "aircraft-performances.json")
with open(fn) as data_file:
    test_data = json.load(data_file)
r.json().set(kn, Path.root_path(), test_data)