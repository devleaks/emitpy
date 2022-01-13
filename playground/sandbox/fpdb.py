"""
Test API for flightplandatabase with request caching.

"""
import os
import json
from geojson import Feature, LineString, Point, FeatureCollection
import argparse

import flightplandb as fpdb
from flightplandb.datatypes import GenerateQuery

import requests_cache

FP_DIR = os.path.join("..", "data", "flightplans")


def to_geojson(fp):
    # convert the route of a flight plan to a geojson feature collection
    # of waypoints and a line segment for the route.
    FT = 0.3048

    route = LineString()
    fc = FeatureCollection(features=[Feature(geometry=route, properties={"name": "plan"})])
    for n in fp["route"]["nodes"]:
        fc.features.append(Feature(geometry=Point((n["lon"], n["lat"], n["alt"]*FT)), properties={
            "type": n["type"],
            "ident": n["ident"],
            "name": n["name"]
        }))
        route.coordinates.append([n["lon"], n["lat"], n["alt"]*FT])
    return fc


def main():
    parser = argparse.ArgumentParser(description="Get flight plan.")
    parser.add_argument("--fromICAO", "-f", nargs="?", type=str, help="departure")
    parser.add_argument("--toICAO", "-t", nargs="?", type=str, help="arrival")

    args = parser.parse_args()

    orig = args.fromICAO.upper()
    dest = args.toICAO.upper()
    fn = "%s-%s" % (args.fromICAO.lower(), args.toICAO.lower())
    ffp = os.path.join(FP_DIR, fn + ".json")
    gfp = os.path.join(FP_DIR, fn + ".geojson")

    # creates file cache
    if not os.path.exists(FP_DIR):
        print("create new fpdb file cache")
        os.mkdir(FP_DIR)

    # if both files cached, returns them
    if os.path.exists(ffp) and os.path.exists(gfp):
        print("cached files exists")
        exit()

    print("no cached files")

    requests_cache.install_cache()
    api = fpdb.FlightPlanDB("vMzb5J3qtRnIo4CgdCqiGUsRhWEXpAHLMJj04Rds")
    plans = api.user.plans(username="devleaks", limit=1000)

    for plan in plans:
        print(plan.fromICAO, plan.toICAO)
        if plan.fromICAO == orig and plan.toICAO == dest:
            print("plan %d found in database" % (plan.id))
            fp = api.plan.fetch(id_=plan.id, return_format="json")
            fpd = json.loads(fp)
            fpgeo = to_geojson(fpd)
            with open(ffp, "w") as outfile:
                outfile.write(fp)
            with open(gfp, "w") as outfile:
                json.dump(fpgeo, outfile)
            print("%d (%s) cached in file" % (fpd["id"], fn))
            exit()

    print("no plan in db, generating %s-%s" % (orig, dest))

    newplan = GenerateQuery(
        fromICAO=orig,
        toICAO=dest,
        cruiseAlt=30000,
        cruiseSpeed=380,
        ascentRate=2500,
        ascentSpeed=250,
        descentRate=1500,
        descentSpeed=250)
    plan = api.plan.generate(newplan)
    if plan:
        fp = api.plan.fetch(id_=plan.id, return_format="json")
        fpd = json.loads(fp)
        fpgeo = to_geojson(fpd)
        with open(ffp, "w") as outfile:
            outfile.write(fp)
        with open(gfp, "w") as outfile:
            json.dump(fpgeo, outfile)
        print("new plan %d (%s) cached in file" % (fpd["id"], fn))


if __name__ == "__main__":
    main()

