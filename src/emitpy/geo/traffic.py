"""Summary
"""

from typing import List
import json

from .features import FeatureWithProps

# from emitpy.emit import EmitPoint


def asTrafficCSV(features: List[FeatureWithProps], header: bool = True) -> str:
    """Convert feature geometry and properties for Traffic package analysis.

    CSV traffic format:

    timestamp,icao24,callsign,latitude,longitude,altitude,groundspeed,track,vertical_rate


    Args:
        features (FeatureWithProps): List of features to convert
        header (bool, optional): Whether to include a first line with column names.

    Returns:
        str: CSV in traffic format
    """
    # mandatory: timestamp, icao24, latitude, longitude, groundspeed, track, vertical_rate, callsign, altitude
    csv = ""
    if header:
        csv = "timestamp,icao24,callsign,latitude,longitude,altitude,groundspeed,track,vertical_rate\n"

    c = features[0]  # constants
    icao24 = c.getProp("icao24")
    callsign = None
    flight = c.getProp("flight")
    if flight is not None:
        callsign = flight.get("callsign")

    for f in features:
        if f.geomtype() == "Point":
            s = f"{int(f.getAbsoluteEmissionTime())},{icao24},{callsign},{f.lat()},{f.lon()},{f.altitude(0)},{f.speed(0)},{f.heading(0)},{f.vspeed(0)}\n"
            csv = csv + s

    return csv


def asTrafficJSON(features: List[FeatureWithProps]):
    """Convert feature geometry and properties for Traffic package analysis (JSON format).

    JSON traffic format:

    {
      "timestamp": 1527693698000,
      "icao24": "484506",
      "latitude": 52.3239704714,
      "longitude": 4.7394234794,
      "groundspeed": 155,
      "track": 3,
      "vertical_rate": 2240,
      "callsign": "TRA051",
      "altitude": 224
    }

    Args:
        features (FeatureWithProps): List of features to convert
        header (bool, optional): Whether to include a first line with column names.

    Returns:
        str: JSON in traffic format
    """
    c = features[0]  # constants
    icao24 = c.getProp("icao24")
    callsign = c.getProp("callsign")

    return json.dumps(
        [
            {
                "timestamp": f.getAbsoluteEmissionTime(),
                "icao24": icao24,
                "latitude": f.lat(),
                "longitude": f.lon(),
                "groundspeed": f.speed(),
                "track": f.heading(),
                "vertical_rate": f.vspeed(),
                "callsign": callsign,
                "altitude": f.altitude(),
            }
            for f in filter(lambda f: f.geometry.type == "Point", features)
        ]
    )


def toTraffic(features: List["EmitPoint"]) -> str:
    """Wrapper around EmitPoint special formatting for Traffic analysis package

    Args:
        features (List["EmitPoint"]): List of features to convert

    Returns:
        str: CSV in traffic format
    """
    return asTrafficCSV(features)
