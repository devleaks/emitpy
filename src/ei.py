import argparse
import sys
import requests
import json
import urllib.parse

parser = argparse.ArgumentParser("ei")
sub_parsers = parser.add_subparsers(dest="command")

#
# CREATE commands
cmd_create = sub_parsers.add_parser("create", help="create queue, flight, service, or mission", aliases=["cre"])
create_parsers = cmd_create.add_subparsers(dest="what")

# QUEUE
create_queue = create_parsers.add_parser("queue", help="create queue")
create_queue.add_argument("name", type=str)
create_queue.add_argument("format", type=str)
create_queue.add_argument("date", type=str, nargs="?", default=None)
create_queue.add_argument("time", type=str, nargs="?", default=None)
create_queue.add_argument("speed", type=float, nargs="?", default=1.0)

# FLIGHT
create_flight = create_parsers.add_parser("flight", help="create flights")
create_flight.add_argument("move", type=str, choices=["arr", "dep", "arrival", "departure"])
create_flight.add_argument("airline", type=str)
create_flight.add_argument("flightnumber", type=str)
create_flight.add_argument("date", type=str)
create_flight.add_argument("time", type=str)
create_flight.add_argument("airport", type=str)
create_flight.add_argument("actype", type=str)
create_flight.add_argument("acreg", type=str)
create_flight.add_argument("acicao", type=str)
create_flight.add_argument("ramp", type=str)
create_flight.add_argument("queue", type=str)
create_flight.add_argument("--doservice", action='store_true', help="creates services associated with this flight")

# SERVICE
create_service = create_parsers.add_parser("service", help="create services")
create_service.add_argument("service", type=str, choices=["fuel", "catering"])
create_service.add_argument("operator", type=str)
create_service.add_argument("date", type=str)
create_service.add_argument("time", type=str)
create_service.add_argument("ramp", type=str)
create_service.add_argument("quantity", type=float, default=1.0)
create_service.add_argument("svmodel", type=str)
create_service.add_argument("svreg", type=str)
create_service.add_argument("svicao", type=str)
create_service.add_argument("queue", type=str)
create_service.add_argument("emit_rate", type=float)

# MISSION
create_mission = create_parsers.add_parser("mission", help="create services")
create_mission.add_argument("mission", type=str, choices=["security", "fire", "emergency"])
create_mission.add_argument("operator", type=str)
create_mission.add_argument("date", type=str)
create_mission.add_argument("time", type=str)
create_mission.add_argument("svmodel", type=str)
create_mission.add_argument("checkpoints", type=str)
create_mission.add_argument("svreg", type=str)
create_mission.add_argument("svicao", type=str)
create_mission.add_argument("queue", type=str)
create_mission.add_argument("emit_rate", type=float)

#
# Special FLIGHT SERVICES commands
create_fltsvc = create_parsers.add_parser("flight_services", help="create all services associated with a flight", aliases=["fs"])
create_fltsvc.add_argument("queue", type=str)
create_fltsvc.add_argument("flight", type=str, help="flight name, no wild card")

#
# RE-EMIT commands
create_emit = create_parsers.add_parser("emit", help="create new emission of existing flight, service, or mission")
create_emit.add_argument("frequency", type=int)
create_emit.add_argument("queue", type=str)
create_emit.add_argument("mark", type=str, help="synchronization mark")
create_emit.add_argument("date", type=str, help="synchronization date")
create_emit.add_argument("time", type=str, help="synchronization time")
create_emit.add_argument("name", type=str, help="movement to re-emit")

#
# RESCHEDULE commands
resched_cmd = sub_parsers.add_parser("resched", help="reschedule a flight, a service, or a mission; for flights, optionnally also reschedule all associated services", aliases=["rs"])
resched_cmd.add_argument("queue", type=str)
resched_cmd.add_argument("movement", type=str, help="flight, service or mission name, no wild card")
resched_cmd.add_argument("mark", type=str, help="synchronization mark")
resched_cmd.add_argument("date", type=str, help="synchronization date")
resched_cmd.add_argument("time", type=str, help="synchronization time")
resched_cmd.add_argument("--doservice", action='store_true', help="reschedule services associated with rescheduled flight (only for flights, has no effect on services or missions)")

#
# LIST commands
list_cmd = sub_parsers.add_parser("list", help="list all entities of same type", aliases=["ls"])
list_what = {
    "flights": "/airport/flights",
    "services": "/airport/services",
    "missions": "/airport/missions",
    "queues": "/queues",
    "formats": "/queues/formats",
    "ramps": "/airport/ramps",
    "checkpoints": "/airport/checkpoints",
    "depots": "/airport/pois",
    "restareas": "/airport/pois",
    "actypes": "/airport/aircraft-types",
    "svtypes": "/airport/service-types",
    "mstypes": "/airport/mission-types",
    "svopers": "/airport/service-handlers",
    "msopers": "/airport/mission-handlers",
    "airlines": "/airport/airlines",
    "airports": "/airport/airports",
    "marks": "/airport/emit/syncmarks"
}
list_cmd.add_argument("what", type=str, choices=list_what.keys())
list_cmd.add_argument("wildcard", type=str, default=None, nargs="?")

#
# DELETE commands
del_cmd = sub_parsers.add_parser("delete", help="show details of an entity", aliases=["del"])
del_cmd.add_argument("what", type=str, choices=["flight", "service", "mission", "queue"])
del_cmd.add_argument("name", type=str)


#
# QUEUE commands
#
# RESET commands
queue_reset = sub_parsers.add_parser("reset", help="reset a queue")
queue_reset.add_argument("what", type=str, choices=["queue"])
queue_reset.add_argument("name", type=str)

# START commands
queue_start = sub_parsers.add_parser("start", help="reset a queue")
queue_start.add_argument("what", type=str, choices=["queue"])
queue_start.add_argument("name", type=str)

# STOP commands
queue_stop = sub_parsers.add_parser("stop", help="reset a queue")
queue_stop.add_argument("what", type=str, choices=["queue"])
queue_stop.add_argument("name", type=str)


def pprint(r):
    if r.status_code == 200:
        t = r.json()
        if "status" in t:
            if t["status"] != 0:
                print("!"*10, r.request.url, r.request.method, "Returned error:")
                print(t)
            else:
                if "message" in t and t["message"] is not None:
                    print(t["message"])
                if "data" in t and t["data"] is not None:
                    print(t["data"])
        else:  # probably just a [(name, value)]
            print(t)
    elif r.status_code != 500:
        print(">"*10, r.status_code, r.request.url, r.request.method, r.json())
    else:
        print("*"*10, r.status_code, r.request.url, r.request.method)


loop = True
while loop:
    s = input("emitpyi $ ")
    if "quit" == s.rstrip():
        loop = False
        continue
    try:
        args = s.split()
        parsed = parser.parse_args(args)
        # print(f"\n{vars(parsed)}")
        url = None
        data = None
        verb = requests.get

        #
        # PREPARE IT
        if parsed.command == "list" or parsed.command == "ls":
            url = list_what[parsed.what]
            if parsed.what == "marks":
                url = url + f"/{urllib.parse.quote(parsed.wildcard)}"

        elif hasattr(parsed, "what") and parsed.what == "queue":
            # special treatment for queues
            if parsed.command == "start":
                verb = requests.put
                url = "/queue/"
                data = {
                  "name": parsed.name,
                  "start": True
                }
            elif parsed.command == "stop":
                verb = requests.put
                url = "/queue/"
                data = {
                  "name": parsed.name,
                  "start": False
                }
            elif parsed.command == "reset":
                verb = requests.put
                url = "/queue/"
                data = {
                  "name": parsed.name
                }
            elif parsed.command in ["delete", "del"]:
                verb = requests.delete
                url = f"/queue/?name={urllib.parse.quote(parsed.name)}"

            elif parsed.command in ["create", "cre"]:
                verb = requests.post
                url = "/queue/"
                data = {
                  "name": parsed.name,
                  "formatter": parsed.format,
                  "queue_date": parsed.date,
                  "queue_time": parsed.time,
                  "speed": parsed.speed,
                  "start": True
                }

        elif parsed.command in ["delete", "del"]:
            verb = requests.delete
            if parsed.what == "flight":
                url = f"/flight/{urllib.parse.quote(parsed.name)}"
            elif parsed.what == "service":
                url = f"/service/{urllib.parse.quote(parsed.name)}"
            elif parsed.what == "mission":
                url = f"/mission/{urllib.parse.quote(parsed.name)}"


        #
        # DO IT
        if url is not None and url != "":
            BASE_URL = "http://127.0.0.1:8000"
            API_KEY = "d06c4f70-439b-4d0d-992a-0a615013d17d"
            if data is not None:
                response = verb(BASE_URL + url, headers = {'api-key': API_KEY}, data=json.dumps(data))
            else:
                response = verb(BASE_URL + url, headers = {'api-key': API_KEY})
            pprint(response)


    except argparse.ArgumentError:
        print("invalid command", s)
