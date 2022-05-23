import os
import json
import redis
import sys
from redis.commands.json.path import Path

r = redis.StrictRedis()

r.select(1)

# flight plan
# for file in ../../data/managedairport/OTHH/flightplans/*.json; do python pf2.py $file; done
fn = os.path.basename(sys.argv[1])
kn = fn.replace(".json", "").replace("-", ":").lower()
with open(sys.argv[1]) as data_file:
    data = json.load(data_file)
    print(fn)
    r.json().set('flightplans:fpdb:'+kn, Path.root_path(), data)


# # flight plans (geojson)
# # for file in ../../data/managedairport/OTHH/flightplans/*.geojson; do python pf2.py $file; done
# fn = os.path.basename(sys.argv[1])
# kn = fn.replace(".geojson", "").replace("-", ":")
# with open(sys.argv[1]) as data_file:
#     data = json.load(data_file)
#     print(fn)
#     r.json().set('flightplans:geojson:'+kn, Path.root_path(), data)

# # airports
# # for file in ../../data/airports/fpdb/*.json; do python pf2.py $file; done
# fn = os.path.basename(sys.argv[1])
# kn = fn.replace(".json", "").replace("-", ":").lower()
# with open(sys.argv[1]) as data_file:
#     data = json.load(data_file)
#     print(fn)
#     r.json().set('flightplans:airports:'+kn, Path.root_path(), data)
