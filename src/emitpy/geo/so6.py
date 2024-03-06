"""Format fight plan to Eurocontrol SO6 format
"""
from __future__ import annotations
import json
import logging
from typing import List
from datetime import datetime

from emitpy.constants import FEATPROP, FLIGHT_SEGMENT
from emitpy.geo.turf import distance
from .features import FeatureWithProps

logger = logging.getLogger("SO6")


# from emitpy.utils import convert
# from emitpy.geo import MovePoint
#
# LFBO_LFPO LFBO LFPO A320 161330 161730 13 103 0 AFR99NZ 180101 180101 2618.339926512 81.37730189759999 2627.9736328139998 71.2373955306 137241184 0 0 0
# LFBO_LFPO LFBO LFPO A320 161730 162650 103 286 0 AFR99NZ 180101 180101 2627.9736328139998 71.2373955306 2679.0738380580005 71.372278725 137241184 0 0 0
# LFBO_LFPO LFBO LFPO A320 162650 165140 286 272 0 AFR99NZ 180101 180101 2679.0738380580005 71.372278725 2829.1657011360003 64.86581655660001 137241184 0 0 0
# LFBO_LFPO LFBO LFPO A320 165140 170120 272 121 0 AFR99NZ 180101 180101 2829.1657011360003 64.86581655660001 2889.9387165659996 92.54969546640001 137241184 0 0 0
# LFBO_LFPO LFBO LFPO A320 170120 170600 121 106 0 AFR99NZ 180101 180101 2889.9387165659996 92.54969546640001 2912.5827026340003 113.76342773459999 137241184 0 0 0
# LFBO_LFPO LFBO LFPO A320 170600 170930 106 104 0 AFR99NZ 180101 180101 2912.5827026340003 113.76342773459999 2915.384169756 147.196558902 137241184 0 0 0
# LFBO_LFPO LFBO LFPO A320 170930 171150 104 58 0 AFR99NZ 180101 180101 2915.384169756 147.196558902 2919.372253416 163.9836237978 137241184 0 0 0
# LFBO_LFPO LFBO LFPO A320 171150 171310 58 40 0 AFR99NZ 180101 180101 2919.372253416 163.9836237978 2924.2666626 165.72030874380002 137241184 0 0 0
# LFBO_LFPO LFBO LFPO A320 171310 171440 40 39 0 AFR99NZ 180101 180101 2924.2666626 165.72030874380002 2926.708374024 160.94548152059997 137241184 0 0 0
# LFBO_LFPO LFBO LFPO A320 171440 171840 39 16 0 AFR99NZ 180101 180101 2926.708374024 160.94548152059997 2924.034506586 146.2381463304 137241184 0 0 0
def meters_to_fl(m: float, rounding: int = -1) -> int:
    """
    Convert meter to feet

    :param      m:    { parameter_description }
    :type       m:    { type_description }

    :returns:   { description_of_the_return_value }
    :rtype:     { return_type_description }
    """
    r = (m / (12 * 0.0254)) / 100
    if rounding != -1:
        r = rounding * round(r / rounding)
    return int(r)


def asSO6CSV(features: List[FeatureWithProps], header: bool = True) -> str:
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
        csv = (
            "segment_id origin destination aircraft timebeginsegement timeendsegment flbeginsegment flendsegment status callsign"
            + "datebeginsegement dateendsegement latbeginsegement lonbeginsegment latendsegment longendsegment flightid seq segmentlength segmentparity\n"
        )

    # common elements
    DATE_FORMAT = "%y%m%d"
    TIME_FORMAT = "%H%M%S"

    f = features[0]  # constants
    callsign = None
    flight = f.getProp("flight")
    if flight is not None:
        callsign = flight.get("callsign")

    # print(json.dumps(f.to_geojson()))

    actype = f.getPropPath("$.flight.aircraft.actype.base-type.actype")  # ICAO A35K
    origin = f.getPropPath("$.flight.departure.icao")
    destination = f.getPropPath("$.flight.arrival.icao")
    dtstr = f.getPropPath("$.flight.scheduled")
    dtdt = datetime.fromisoformat(dtstr)
    start = dtdt.timestamp()
    segmentid = f"{origin}_{destination}"
    flightidstr: str = f.getPropPath("$.flight.identifier")
    flightid = f"{ int( ''.join([i for i in flightidstr if i.isdigit()]) ) }"  # only keeps digit
    print(">>>>>>>>", flightidstr, flightid, actype, origin, destination)

    # Point elements
    seq = 0
    status = 0
    last = None
    for f in features:
        # Must only consider flight plan points, not move points.
        #
        if f.geomtype() == "Point":
            if last is None:
                last = f
                continue

            seq = seq + 1
            if f.getProp(FEATPROP.PLAN_SEGMENT_TYPE) == FLIGHT_SEGMENT.CRUISE.value:
                status = 1  # we're cruising
            elif status == 1 and f.getProp(FEATPROP.PLAN_SEGMENT_TYPE) != FLIGHT_SEGMENT.CRUISE.value:
                status = 2  # we're descending

            dbegin = last.time()
            dend = f.time()
            if dbegin is None or dend is None:
                logger.warning(f"no time information")
                continue

            timebeginsegement = datetime.fromtimestamp(dbegin + start).strftime(TIME_FORMAT)
            timeendsegment = datetime.fromtimestamp(dend + start).strftime(TIME_FORMAT)

            flbeginsegment = meters_to_fl(last.altitude())
            flendsegment = meters_to_fl(f.altitude())

            datebeginsegement = datetime.fromtimestamp(dbegin + start).strftime(DATE_FORMAT)
            dateendsegement = datetime.fromtimestamp(dend + start).strftime(DATE_FORMAT)

            latbeginsegement = last.lat()
            lonbeginsegment = last.lon()
            latendsegment = f.lat()
            longendsegment = f.lon()

            segmentlength = distance(last, f)
            segmentparity = "0"  # 0-9 color coded

            res = [
                str(f)
                for f in [
                    segmentid,
                    origin,
                    destination,
                    actype,
                    timebeginsegement,
                    timeendsegment,
                    flbeginsegment,
                    flendsegment,
                    status,
                    callsign,
                    datebeginsegement,
                    dateendsegement,
                    latbeginsegement,
                    lonbeginsegment,
                    latendsegment,
                    longendsegment,
                    flightid,
                    seq,
                    segmentlength,
                    segmentparity,
                ]
            ]
            print(res)
            s = " ".join(res)
            csv = csv + s

    return csv


def asSO6JSON(features: List[FeatureWithProps]) -> str:
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
                "track": f.heading_or_course(),
                "vertical_rate": f.vspeed(),
                "callsign": callsign,
                "altitude": f.altitude() * 3.28084,
            }
            for f in filter(lambda f: f.geometry.type == "Point", features)
        ]
    )


def toSO6(features: List["EmitPoint"]) -> str:
    """Wrapper around EmitPoint special formatting for Traffic analysis package

    Args:
        features (List["EmitPoint"]): List of features to convert

    Returns:
        str: CSV in traffic format
    """
    return asSO6CSV(features)
