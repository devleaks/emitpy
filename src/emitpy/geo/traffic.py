from .features import FeatureWithProps

def asTrafficCSV(features: [FeatureWithProps], header: bool = True):
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


def toTraffic(features: ["EmitPoint"]):
    return asTrafficCSV(features) # asTrafficCSV, asTrafficJSON, asFeatureLineStringWithTimestamps,
