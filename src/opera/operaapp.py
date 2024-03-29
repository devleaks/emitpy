import logging
import os
import glob
import csv
import json
import re
import io
import sys
from datetime import datetime

from tabulate import tabulate

sys.path.append("../../src")

from emitpy.geo import FeatureWithProps, point_in_polygon, asFeature
from emitpy.utils import show_path
from emitpy.parameters import MANAGED_AIRPORT_AODB, MANAGED_AIRPORT_DIR, AERODROME_PERIMETER_INDENTITY

from opera.rule import Rule, Event
from opera.aoi import AreasOfInterest
from opera.vehicle import StoppedMessage, Vehicle


FORMAT = "%(levelname)1.1s%(module)15s:%(funcName)-15s%(lineno)4s| %(message)s"
logging.basicConfig(level=logging.DEBUG, format=FORMAT)

logger = logging.getLogger("Opera")


class OperaApp:
    """Opera is a coordination class that loads necessary data (areas of interest, rules)
    and monitor vehicle movement.

    [description]
    """

    def __init__(self, airport):
        self._inited = False
        self.airport = airport

        self.aois = {}
        self.all_aois = set()
        self.rules = {}
        self.vehicle_events = {}  # simpler access for vehicles

        # Working variables
        self.airport_perimeter = None
        self.vehicles = {}

        self.init()

    def init(self) -> bool:
        self.load_aois()
        self.airport_perimeter = asFeature(list(filter(lambda f: f.get_id() == AERODROME_PERIMETER_INDENTITY, self.all_aois))[0])
        self.load_rules()
        self._inited = True
        return self._inited

    def load_aois(self):
        # will get aois from airport later
        #
        gfs_dir = os.path.join(MANAGED_AIRPORT_DIR, "geometries", "opera-*.geojson")
        for filename in glob.glob(gfs_dir):
            name = filename.replace(".geojson", "")
            self.aois[name] = AreasOfInterest(filename=filename, name=name)
            self.all_aois = self.all_aois.union(self.aois[name].features)
        logger.debug(f"{len(self.aois)} aois files loaded, {len(self.all_aois)} aois")

    def select_aoi(self, pattern):
        ret = set(filter(lambda f: re.match(pattern, f.get("id", "")), self.all_aois))
        # logger.debug(f"{pattern} => {[f.get_id() for f in ret]}")
        return ret

    def add_rule(
        self, name: str, vehicles: str, start_action: str, start_aois: str, end_action: str, end_aois: str, same_aoi: bool, timeout: float, notes: str = None
    ):
        logger.debug(f"adding rule {name} {vehicles}..")
        vevents = self.vehicle_events.get(vehicles, [])
        timeout = float(timeout) * 60 if timeout != "" else 0
        aois_start = self.select_aoi(start_aois)
        logger.debug(f"{len(aois_start)} aois_start")
        start_event = Event(vehicles=vehicles, action=start_action, aois=aois_start, aoi_selector=start_aois)
        vevents.append(start_event)
        aois_end = self.select_aoi(end_aois)
        logger.debug(f"{len(aois_end)} aois_end")
        end_event = Event(vehicles=vehicles, action=end_action, aois=aois_end, aoi_selector=end_aois)
        vevents.append(end_event)
        rule = Rule(name=name, start=start_event, end=end_event, same_aoi=same_aoi, timeout=timeout, notes=notes)
        self.rules[rule.get_id()] = rule
        self.vehicle_events[vehicles] = vevents
        logger.debug(f"..added")

    def delete_rule(self, name):
        # self.rules[name]._enabled = False
        del self.rules[name]

    def load_rules(self):
        fn = os.path.join(MANAGED_AIRPORT_DIR, "opera", "rules.csv")
        with open(fn, "r") as file:
            for row in csv.DictReader(file):
                if row["name"].startswith("#"):  # comment
                    continue
                vehicles = row["vehicles"]
                logger.debug(f"rule {row['name']} {vehicles}")
                if vehicles == "" or vehicles == "*":
                    vehicles = "(.*)"  # re
                same_aoi = (row["same_aoi"] == "") or (row["same_aoi"].lower() in ["true", "on", "yes"])

                self.add_rule(
                    name=row["name"],
                    vehicles=vehicles,
                    start_action=row["action1"],
                    start_aois=row["area1"],
                    end_action=row["action2"],
                    end_aois=row["area2"],
                    same_aoi=same_aoi,
                    timeout=row["timeout"],
                    notes=row["note"],
                )

        logger.debug(f"{len(self.rules)} rules loaded")

    def process(self, position):
        """Analyze new position.

        Position is assumed to be within the airport perimeter (no check).

        [description]

        Args:
            position ([type]): [description]
        """
        if not point_in_polygon(position, self.airport_perimeter):
            return []

        icao24 = position.getProp("icao24")
        if icao24 is None:
            logger.warning("vehicle has no icao24")
            return []
        vehicle = self.vehicles.get(icao24, Vehicle(identifier=icao24))
        self.vehicles[vehicle.identifier] = vehicle
        logger.debug(f"vehicle is {vehicle.identifier}")
        vehicle.set_aircraft(self.guess_vehicle_type(position))
        vehicle.set_id(self.get_vehicle_identity(position))
        vehicle.init(self)
        ret = vehicle.at(position)
        logger.debug(f"generated {len(ret)} messages")
        return ret

    def guess_vehicle_type(self, position):
        ret = "aircraft" in position.properties
        logger.debug(f"is_aircraft {ret}")
        return ret

    def get_vehicle_identity(self, position):
        ident = None
        if "flight" in position.properties:
            ident = position.getPropPath("flight.aircraft.identity")
        elif "mission" in position.properties:
            ident = position.getPropPath("mission.vehicle.identity")
        elif "service" in position.properties:
            ident = position.getPropPath("service.vehicle.identity")

        if ident is not None:
            logger.debug(f"identity {ident}")
        else:
            logger.warning(f"no identity in {position}")
        return ident

    def bulk_process(self, positions):
        """Bulk processes a whole track for a single vehicle.

        During bulk processing, all positions are coming from the same vehicle.

        Args:
            positions ([type]): [description]

        Returns:
            [type]: [description]
        """
        first_pos = positions[0]
        vehicle_id = first_pos.getProp("icao24")
        if vehicle_id is None:
            logger.debug("vehicle has no icao24")
            return
        vehicle = self.vehicles.get(vehicle_id, Vehicle(identifier=vehicle_id))
        self.vehicles[vehicle.identifier] = vehicle
        logger.debug(f"vehicle is {vehicle.identifier}")

        # Filter only position at or around airport perimeter
        positions_at_airport = filter(lambda f: point_in_polygon(f, self.airport_perimeter), positions)
        positions_at_airport = sorted(positions_at_airport, key=lambda x: x.get_timestamp())
        logger.debug(f"processing {len(list(positions_at_airport))}/{len(positions)}")

        # Sets what the vehicle has to report
        vehicle.set_aircraft(self.guess_vehicle_type(first_pos))
        vehicle.set_id(self.get_vehicle_identity(first_pos))
        vehicle.init(self)

        # Ask vehicle to report events
        i = 0
        for f in positions_at_airport:
            logger.debug(f"vehicle {vehicle.identifier}: processing line {i}, at {f.get_timestamp()}")
            messages = vehicle.at(f)
            i = i + 1

        logger.info(
            f"total: resolved {len(self.rules)} rules {len(vehicle.resolves)} times for {len(self.vehicles)} vehicles (got {len(vehicle.messages)} messages)"
        )
        self.printMessages(vehicle)
        self.printRules(vehicle)

    def printMessages(self, vehicle):
        """Print all resolved rules to file for later processing with all details.

        Would be a confortable pandan DataFrame
        """
        table = []
        messages = sorted(vehicle.messages, key=lambda m: m.get_timestamp())
        for m in vehicle.messages:
            line = []
            if type(m) == StoppedMessage:
                line.append("")
                line.append("")
                line.append("")
                line.append("stopped")
                line.append(vehicle.get_id())
                if m.aoi is not None:
                    line.append(m.aoi.get_id())
                else:
                    line.append("")
                dt = datetime.fromtimestamp(m.get_timestamp()).replace(microsecond=0)
                line.append(dt)
            else:
                event = m.event
                rule = event.rule
                line.append(rule.get_id())
                line.append(rule.notes)
                line.append("start" if event.is_start() else "end")
                line.append(event.action)
                line.append(m.vehicle.get_id())
                line.append(m.aoi.get_id())
                dt = datetime.fromtimestamp(m.get_timestamp()).replace(microsecond=0)
                line.append(dt)
            table.append(line)
        table = sorted(table, key=lambda x: x[0])

        output = io.StringIO()
        print("\n", file=output)
        print(f"MESSAGES for {vehicle.get_id()}", file=output)
        headers = ["rule", "purpose", "e.start", "action", "vehicle", "aoi", "time"]
        print(tabulate(table, headers=headers), file=output)
        contents = output.getvalue()
        output.close()
        logger.info(f"{contents}")

    def printRules(self, vehicle):
        """Print all resolved rules to file for later processing with all details.

        Would be a confortable pandan DataFrame
        """
        table = []
        for r in vehicle.resolves:
            line = []
            rule = r.promise.rule
            line.append(rule.get_id())
            line.append(rule.notes)
            line.append(r.promise.vehicle.get_id())
            line.append(rule.start.action)
            line.append(r.promise.data.aoi.get_id())
            line.append(rule.end.action)
            line.append(r.data.aoi.get_id())
            dt = datetime.fromtimestamp(r.promise.get_timestamp()).replace(microsecond=0)
            line.append(dt)
            line.append(round(r.get_timestamp() - r.promise.get_timestamp()))
            # line.append(r.promise.get_id())
            # line.append(r._ident)
            table.append(line)
        table = sorted(table, key=lambda x: x[0])

        output = io.StringIO()
        print("\n", file=output)
        print(f"RESOLVED RULES", file=output)
        headers = ["rule", "purpose", "vehicle", "start", "s aoi", "end", "e aoi", "time", "duration"]  # , "promise id", "resolve id"]
        print(tabulate(table, headers=headers), file=output)
        contents = output.getvalue()
        output.close()
        logger.info(f"{contents}")

    def save(self):
        """Saves messages and resolutions into files"""
        self.saveMessages()
        self.saveRules()

    def saveMessages(self):
        """Saves messages to file."""
        DATABASE = "events"
        basename = os.path.join(MANAGED_AIRPORT_AODB, DATABASE)
        if not os.path.isdir(basename):
            os.mkdir(basename)
            logger.info(f"{basename} created")

        headers = ["rule", "purpose", "e.start", "action", "vehicle", "aoi", "time"]
        table = []
        for v in self.vehicles.values():
            for m in v.messages:
                line = []
                if type(m) == StoppedMessage:
                    line.append("")  # 0
                    line.append("")
                    line.append("")
                    line.append("stopped")
                    line.append(v.get_id())
                    if m.aoi is not None:
                        line.append(m.aoi.get_id())
                    else:
                        line.append("")
                    dt = datetime.fromtimestamp(m.get_timestamp()).replace(microsecond=0)
                    line.append(dt)  # 6
                else:
                    event = m.event
                    rule = event.rule
                    line.append(rule.get_id())  # 0
                    line.append(rule.notes)
                    line.append("start" if event.is_start() else "end")
                    line.append(event.action)
                    line.append(m.vehicle.get_id())
                    line.append(m.aoi.get_id())
                    dt = datetime.fromtimestamp(m.get_timestamp()).replace(microsecond=0)
                    line.append(dt)  # 6
                table.append(line)
            table = sorted(table, key=lambda x: x[6])
            table.insert(0, headers)
            fn = os.path.join(basename, v.get_id() + ".csv")
            with open(fn, "w") as fp:
                writer = csv.writer(fp)
                writer.writerows(table)

    def saveRules(self):
        """Saves resolutions to file."""
        DATABASE = "rules"
        basename = os.path.join(MANAGED_AIRPORT_AODB, DATABASE)
        if not os.path.isdir(basename):
            os.mkdir(basename)
            logger.info(f"{basename} created")

        headers = ["rule", "purpose", "vehicle", "start", "start_aoi", "end", "end_aoi", "time", "duration"]
        table = []
        for v in self.vehicles.values():
            for r in v.resolves:
                line = []
                rule = r.promise.rule
                line.append(rule.get_id())  # 0
                line.append(rule.notes)
                line.append(r.promise.vehicle.get_id())
                line.append(rule.start.action)
                line.append(r.promise.data.aoi.get_id())
                line.append(rule.end.action)
                line.append(r.data.aoi.get_id())
                dt = datetime.fromtimestamp(r.promise.get_timestamp()).replace(microsecond=0)
                line.append(dt)  # 7
                line.append(round(r.get_timestamp() - r.promise.get_timestamp()))
                table.append(line)
            table = sorted(table, key=lambda x: x[7])
            table.insert(0, headers)
            fn = os.path.join(basename, v.get_id() + ".csv")
            with open(fn, "w") as fp:
                writer = csv.writer(fp)
                writer.writerows(table)


if __name__ == "__main__":
    DATABASE = "missions"
    FILE_EXTENSION = "6-broadcast.json"

    opera = OperaApp(airport=None)

    basename = os.path.join(MANAGED_AIRPORT_AODB, DATABASE)
    data_dir = os.path.join(basename, "*" + FILE_EXTENSION)
    for filename in glob.glob(data_dir):
        data = {}
        print(filename)
        with open(filename, "r") as file:
            arr = file.readlines()
            data = []
            for a in arr:
                data.append(json.loads(a))
        data = [FeatureWithProps.new(p) for p in data]
        # for filename in glob.glob(data_dir):
        #     data = {}
        #     logger.debug(f"{'>' * 20} {show_path(filename)}")
        #     with open(filename, "r") as file:
        #         data = json.load(file)
        #     data = [FeatureWithProps.new(p) for p in data]
        opera.bulk_process(data)
    opera.save()
