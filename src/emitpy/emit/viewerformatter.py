#  Python classes to format features for output to different channel requirements
#
import logging
from datetime import datetime
import json

from ..constants import FEATPROP
from ..airport import Airport

from .format import Formatter

logger = logging.getLogger("ViewerFormatter")


class ViewerFormatter(Formatter):

    FILE_EXTENTION = "csv"

    def __init__(self, feature: "FeatureWithProps"):
        Formatter.__init__(self, feature=feature)
        # rename a few properties for viewer:
        f = feature

        # Identity
        f.setProp("classId", "aircrafts")
        f.setProp("typeId", "AIRCRAFT")
        f.setProp("orgId", feature.getProp("aircraft:operator:name"))
        f.setProp("name", f.getProp("aircraft:icao24"))
        # Movement
        f.setProp("altitude", feature.altitude())
        # Display organisation
        f.setProp("group_name", "AIRCRAFTS")
        f.setProp("status", "ACTIVE")
        f.setProp("_timestamp_emission", datetime.now().isoformat())

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
            "elapsed": f.getProp("emit_relative_time"),
            "vertex": f.getProp("move-index"),
            "sequence": f.getProp("emit-index"),
            "category": "e",
            "speed": f.speed(),
            "bearing": f.getProp("heading"),
            "note": f.getProp("_mark"),
            "device": f.getProp("icao24"),
            "adsb": f.getProp("icao24"),
            "model": f.getProp("aircraft:actype:actype"),
            "registration": f.getProp("aircraft:acreg"),
            "movement": f.getProp("flightnumber").replace(" ",""),
            "handler": "nohandler",
            "operator": f.getProp("airline:name"),
            "alt": f.altitude()
        })

    def __str__(self):
        return json.dumps({
            "source": "EMITPY",
            "topic": "gps/aircrafts",
            "type": "map",
            "timestamp": datetime.now().isoformat(),
            "payload": self.feature
        })

"""
EMIT PRODUCES EMIT POINTS: (Feature(<Point>))
=========================
{
    "type": "Feature",
    "geometry":
    {
        "type": "Point",
        "coordinates": [51.6032, 25.270022]
    },
    "properties":
    {
        "name": "266",
        "speed": 10,
        "marker-color": "#eeeeee",
        "marker-size": "medium",
        "marker-symbol": "",
        "_mark": "taxi",
        "_taxiways": "266",
        "time": 23223.24378108089,
        "saved-time": 113.53146227719107,
        "emit_relative_time": 23257.50824458422,
        "emit-index": 912,
        "broadcast": false,
        "emit-reason": "at vertex 137, e=912",
        "identifier": "QR196-S202204041400",
        "airline:orgId": "Qatar Airways",
        "airline:classId": "airline",
        "airline:typeId": "",
        "airline:name": "QR",
        "departure:icao": "EBBR",
        "departure:iata": "BRU",
        "departure:name": "Brussels Airport",
        "departure:city": "Brussels",
        "departure:country": "BE",
        "arrival:icao": "OTHH",
        "arrival:iata": "DOH",
        "arrival:name": "Hamad International Airport",
        "arrival:city": "Doha",
        "arrival:country": "Qatar",
        "aircraft:actype:actype-manufacturer": "Airbus",
        "aircraft:actype:actype": "A30B",
        "aircraft:actype:acmodel": "A300-200 (A300-C4-200. F4-200)",
        "aircraft:operator:orgId": "Qatar Airways",
        "aircraft:operator:classId": "airline",
        "aircraft:operator:typeId": "",
        "aircraft:operator:name": "QR",
        "aircraft:acreg": "A7-PMA",
        "aircraft:ident": null,
        "aircraft:icao24": "efface",
        "icao24": "efface",
        "flightnumber": "QR 196",
        "codeshare": null,
        "ramp:name": "E15",
        "ramp:apron": "E",
        "runway:name": "34L",
        "heading": 68.29022013063096
    }
}

VIEWER EXPECTS MESSAGES
=======================
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
