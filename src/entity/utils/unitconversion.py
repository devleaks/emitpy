"""
Conversion utility functions.
Why doesn't airline business use MKSA?
There are only 3 countries in the world that are still officially using the imperial system: The United States of America, Myanmar, and Liberia.
"""

# Geology constants
R = 6371000            # Approximate average radius of third rock from the sun, in metres

########################################
# Units, etc
#
FT = 12 * 0.0254       # 1 foot = 12 inches
NAUTICAL_MILE = 1.852  # Nautical mile in meters 6076.118ft=1nm. Easy.


def toNm(m):
    """
    Convert meter to nautical miles

    :param      m:    { parameter_description }
    :type       m:    { type_description }

    :returns:   { description_of_the_return_value }
    :rtype:     { return_type_description }
    """
    return round(m / NAUTICAL_MILE)


def toFeet(m):
    """
    Convert meter to feet

    :param      m:    { parameter_description }
    :type       m:    { type_description }

    :returns:   { description_of_the_return_value }
    :rtype:     { return_type_description }
    """
    return round(m / FT)


def toMeter(f):
    """
    Convert feet to meters

    :param      f:    { parameter_description }
    :type       f:    { type_description }

    :returns:   { description_of_the_return_value }
    :rtype:     { return_type_description }
    """
    return round(ft * FT)


def toKn(kmh):
    """
    Convert kilometer per hours into knots

    :param      kmh:  The kilometers per hour
    :type       kmh:  { type_description }

    :returns:   { description_of_the_return_value }
    :rtype:     { return_type_description }
    """
    return kmh / NAUTICAL_MILE


def toKmh(kn):
    return kn * NAUTICAL_MILE


def convertAngleTo360(alfa):
    """
    Convert degree angle value to 0-359° value.

    :param      alfa:  The alfa
    :type       alfa:  { type_description }

    :returns:   { description_of_the_return_value }
    :rtype:     { return_type_description }
    """
    beta = alfa % 360
    if beta < 0:
        beta = beta + 360
    return beta


def turnAngle(bi, bo):
    t = bi - bo
    if t < 0:
        t += 360
    if t > 180:
        t -= 360
    return t


def sign(x):
    """
    there is no sign function in python...

    :param      x:    { Value to find sign for }
    :type       x:    { number }

    :returns:   { -1, 0, 1 }
    :rtype:     { int }
    """
    if x < 0:
        return -1
    elif x > 0:
        return 1
    return 0


def ConvertDMSToDD(degrees, minutes, seconds, direction):
    dd = float(degrees) + float(minutes)/60 + float(seconds)/(60*60)
    return dd if direction in ("N", "E") else dd * -1


def FLtoM(fl: int):
    return fl * FT / 100


def mach(mach: float, altitude: int = 30000):
    mph_machconvert = mach * 660
    kmh_machconvert = mach * 1062
    knots_machconvert = mach * 573

    if altitude >= 40000:
        mph_machconvert = mach * 660
        kmh_machconvert = mach * 1062
        knots_machconvert = mach * 573

    elif altitude >= 35000:
        mph_machconvert = mach * 664
        kmh_machconvert = mach * 1069
        knots_machconvert = mach * 577

    elif altitude >= 30000:
        mph_machconvert = mach * 679
        kmh_machconvert = mach * 1093
        knots_machconvert = mach * 590

    elif altitude >= 25000:
        mph_machconvert = mach * 693
        kmh_machconvert = mach * 1116
        knots_machconvert = mach * 602

    elif altitude >= 20000:
        mph_machconvert = mach * 707
        kmh_machconvert = mach * 1138
        knots_machconvert = mach * 614

    elif altitude >= 15000:
        mph_machconvert = mach * 721
        kmh_machconvert = mach * 1161
        knots_machconvert = mach * 627

    elif altitude >= 10000:
        mph_machconvert = mach * 735
        kmh_machconvert = mach * 1182
        knots_machconvert = mach * 638

    elif altitude >= 0:
        mph_machconvert = mach * 762
        kmh_machconvert = mach * 1223
        knots_machconvert = mach * 660

    else:
        mph_machconvert = mach * 660
        kmh_machconvert = mach * 1062
        knots_machconvert = mach * 573

    return (kmh_machconvert, knots_machconvert, mph_machconvert)


def machToKmh(mach: float, altitude: int = 30000):
    """
    Convert MACH speed to ground speed for different altitude ranges.
    Altitude should be supplied in feet ASL.
    Returns kilometers per hour.

    :param      mach:      The mach
    :type       mach:      float
    :param      altitude:  The altitude
    :type       altitude:  int

    :returns:   { description_of_the_return_value }
    :rtype:     { return_type_description }
    """
    c = mach(mach, alt)
    return c[0]

