import logging
import os
import glob
import csv
import json
import re
import sys

sys.path.append("../../src")

from emitpy.geo import FeatureWithProps, point_in_polygon, line_intersect_polygon, mkFeature

from rule import Rule, Event
from aoi import AreasOfInterest
from vehicle import Vehicle

logger = logging.getLogger("Opera")
logging.basicConfig(level=logging.DEBUG)


class Opera:
    """Opera is a coordination class that loads necessary data (areas of interest, rules)
    and monitor vehicle movement.

    [description]
    """

    def __init__(self, airport):
        self._inited = False
        self.airport = airport

        self.aois = {}
        self.all_aois = []
        self.rules = []
        self.vehicle_events = {}

        # Working variables
        self.airport_perimeter = None
        self.vehicles = {}

        self._last_pos = {}  # { vehicle_identity : position }
        self._promises = []

        # Result variables
        self._resolves = []

        self.init()

    def init(self) -> bool:
        self.load_aois()
        self.airport_perimeter = mkFeature(list(filter(lambda f: f["id"] == "OTHH:aerodrome:aerodrome:perimeter", self.all_aois))[0])
        self.load_rules()
        self._inited = True

    def load_aois(self):
        # will get aois from airport later
        #
        gfs_dir = os.path.join("data", "*.geojson")
        for filename in glob.glob(gfs_dir):
            name = filename.replace(".geojson", "")
            self.aois[name] = AreasOfInterest(filename=filename, name=name)
            self.all_aois = self.all_aois + self.aois[name].features
        logger.debug(f"{len(self.aois)} aois loaded")

    def load_rules(self):
        with open("data/rules.csv", "r") as file:
            for row in csv.DictReader(file):
                vehicles = row["vehicles"]
                if vehicles == "" or vehicles == "*":
                    vehicles = "(.*)"  # re
                vevents = self.vehicle_events.get(vehicles, [])

                timeout = float(row["timeout"]) if row["timeout"] != "" else 0

                aois_start = filter(lambda f: re.match(row["area1"], f.get("id", "")), self.all_aois)
                logger.debug(f"{len(list(aois_start))} aois_start")
                start_event = Event(vehicles=vehicles, action=row["action1"], aois=aois_start)
                vevents.append(start_event)

                aois_end = filter(lambda f: re.match(row["area2"], f.get("id", "")), self.all_aois)
                logger.debug(f"{len(list(aois_end))} aois_end")
                end_event = Event(vehicles=vehicles, action=row["action2"], aois=aois_end)
                vevents.append(end_event)

                rule = Rule(name=row["name"], start=start_event, end=end_event, timeout=timeout, notes=row["note"])
                self.rules.append(rule)
                self.vehicle_events[vehicles] = vevents

        logger.debug(f"{len(self.rules)} rules loaded")

    def process(self, position):
        """Analyze new position.

        Position is assumed to be within the airport perimeter (no check).

        [description]

        Args:
            position ([type]): [description]
        """

    def get_identity(self, position):
        t = position.getPropPath("flight.aircraft.identity")
        logger.debug(f"identity {t}")
        return t

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
        logger.debug(f"vehicle is {vehicle.identifier}")

        # Filter only position at or around airport perimeter
        positions_at_airport = filter(lambda f: point_in_polygon(f, self.airport_perimeter), positions)
        positions_at_airport = sorted(positions_at_airport, key=lambda x: x.getProp("emit-absolute-time"))
        logger.debug(f"processing {len(list(positions_at_airport))}/{len(positions)}")

        # Sets what the vehicle has to report
        vehicle.set_ident(self.get_identity(first_pos))
        vehicle.init(self)

        # Ask vehicle to report events
        for f in positions_at_airport:
            events = vehicle.at(f)
            # From events, check is new promise or resolve


if __name__ == "__main__":
    opera = Opera(airport=None)
    data = {}
    with open("data/test.txt", "r") as file:
        arr = file.readlines()
        data = []
        for a in arr:
            data.append(json.loads(a))
    data = [FeatureWithProps.new(p) for p in data]
    opera.bulk_process(data)
