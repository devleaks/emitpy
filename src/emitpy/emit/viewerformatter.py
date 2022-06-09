#  Python classes to format features for output to different channel requirements
#
import logging
from datetime import datetime
import json

from emitpy.constants import FEATPROP
from emitpy.airport import Airport

from .format import Formatter

logger = logging.getLogger("ViewerFormatter")


class ViewerFormatter(Formatter):
    """
    Viewer expects messages like these:

    [
    {
        "source": "GIPSIM",
        "topic": "aodb/moveinfo",
        "type": "flightboard",
        "timestamp": "2022-04-04T09:51:00.000+02:00",
        "payload":
        {
            "info": "scheduled",
            "move": "departure",
            "flight": "XM0631",
            "operator": "XM0",
            "airport": "CMN",
            "date": "2022-04-04",
            "time": "15:51",
            "parking": "G2R",
            "timestamp": "2022-04-04T09:51:00.000+02:00"
        }
    },
    {
        "source": "GIPSIM",
        "topic": "gps/aircrafts",
        "type": "map",
        "timestamp": "2022-04-04T12:27:33.047+02:00",
        "payload":
        {
            "source": "GIPSIM",
            "type": "Feature",
            "properties":
            {
                "name": "051210",
                "typeId": "AIRCRAFT",
                "classId": "aircrafts",
                "orgId": "QR",
                "heading": 338.4,
                "speed": 280.59,
                "group_name": "AIRCRAFTS",
                "status": "ACTIVE",
                "_timestamp_emission": "2022-04-04T12:27:33.047+02:00",
                "_style": [],
                "altitude": "42.24474666593332",
                "payload":
                {
                    "emit": true,
                    "marker-color": "#ff2600",
                    "marker-size": "medium",
                    "marker-symbol": "",
                    "nojitter": [51.708418822241256, 25.069189243485194, 42.24474666593332],
                    "elapsed": 840.0000000000005,
                    "vertex": 50,
                    "sequence": 30,
                    "category": "e",
                    "speed": 280.592002964627,
                    "bearing": 338.4,
                    "note": "en route",
                    "device": "051210",
                    "adsb": "051210",
                    "model": "B744",
                    "registration": "N-228",
                    "movement": "QR0118",
                    "handler": "nohandler",
                    "operator": "QR",
                    "alt": 42.24474666593332
                }
            },
            "geometry":
            {
                "type": "Point",
                "coordinates": []
            }
        }
    }
    """

    FILE_EXTENTION = "csv"

    def __init__(self, feature: "FeatureWithProps"):
        Formatter.__init__(self, feature=feature)
        # rename a few properties for viewer:
        self.name = "js-viewer"
        f = self.feature

        # Identity
        f.setProp(FEATPROP.CLASS_ID.value, "aircrafts")
        f.setProp(FEATPROP.TYPE_ID.value, "AIRCRAFT")
        f.setProp(FEATPROP.ORG_ID.value, feature.getProp("aircraft:operator:name"))
        f.setProp(FEATPROP.NAME.value, f.getProp("aircraft:icao24"))
        # Movement
        f.setProp("altitude", feature.altitude())
        # Display organisation
        f.setProp("group_name", "AIRCRAFTS")
        f.setProp("status", "ACTIVE")
        f.setProp("_timestamp_emission", datetime.now().astimezone().isoformat())

        f.setProp("_style", {
            "markerColor": "#00a",
            "weight": 1,
            "opacity": 0.8,
            "fillColor": "rgb(0,0,0)",
            "fillOpacity": 0.4,
            "markerSymbol": "plane",
            "markerRotationOffset": 0
        })

        f.setProp("payload", {
            "emit": True,
            "nojitter": self.feature["geometry"]["coordinates"],
            "elapsed": f.getProp(FEATPROP.EMIT_REL_TIME.value),
            "vertex": f.getProp(FEATPROP.MOVE_INDEX.value),
            "sequence": f.getProp(FEATPROP.EMIT_INDEX.value),
            "category": "e",
            "speed": f.speed(),
            "bearing": f.getProp(FEATPROP.HEADING.value),
            "note": f.getProp(FEATPROP.MARK.value),
            "device": f.getProp(FEATPROP.ICAO24.value),
            "adsb": f.getProp(FEATPROP.ICAO24.value),
            "model": f.getProp("aircraft:actype:actype"),
            "registration": f.getProp("aircraft:acreg"),
            "movement": f.getProp("flightnumber").replace(" ",""),
            "handler": "nohandler",
            "operator": f.getProp("airline:name"),
            "alt": f.altitude(),
            "emitpy-format": self.name
        })

    def __str__(self):
        return json.dumps({
            "source": "EMITPY",
            "topic": "gps/aircrafts",
            "type": "map",
            "timestamp": datetime.now().astimezone().isoformat(),
            "payload": self.feature
        })

