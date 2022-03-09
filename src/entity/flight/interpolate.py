import logging
from datetime import timedelta

from turfpy.measurement import distance


logger = logging.getLogger("interpolate")


def interpolate_value(arr, value, istart, iend):
    startval = arr[istart].getProp(value)  # first known speed
    endval = arr[iend].getProp(value)  # last known speed

    if startval is None:
        logger.warning(":interpolate_value: istart has no value %s" % (arr[istart]))
    if endval is None:
        logger.warning(":interpolate_value: iend has no value %s" % (arr[iend]))

    if startval == endval:  # simply copy
        for idx in range(istart, iend):
            arr[idx].setProp(value, startval)
            # logger.debug(":interpolate_value: copied %f (%d) -> (%d)f" % (startval, istart, iend))
        return

    ratios = {}
    cumul_dist = 0
    for idx in range(istart+1, iend):
        d = distance(arr[idx-1], arr[idx], "m")
        cumul_dist = cumul_dist + d
        ratios[idx] = cumul_dist
    # logger.debug(":interpolate_value: (%d)%f -> (%d)%f, %f" % (istart, startval, iend, endval, cumul_dist))
    if cumul_dist != 0:
        speed_a = (endval - startval) / cumul_dist
        speed_b = startval
        for idx in range(istart+1, iend):
            # logger.debug(":interpolate_value: %d %f %f %f" % (idx, ratios[idx], ratios[idx]/cumul_dist, speed_b + speed_a * ratios[idx]))
            arr[idx].setProp(value, speed_b + speed_a * ratios[idx])
    else:
        logger.warning(":interpolate_value: cumulative distance is 0: %d-%d" % (istart, iend))


def interpolate(arr: list, value: str):
    """
    Compute interpolated values for altitude and speed based on distance.
    This is a simple linear interpolation based on distance between points.
    Runs for flight portion of flight.
    """
    # we do have a speed for first point in flight for both arrival (takeoff_speed, apt.alt) and departure (landing_speed, apt.alt)
    noval_idx = None  # index of last elem with not speed, elem[0] has speed.
    for idx in range(1, len(arr)):
        f = arr[idx]

        s = f.getProp(value)
        if s is None:
            if noval_idx is None:
                noval_idx = idx - 1
        else:
            if noval_idx is not None:
                interpolate_value(arr, value, noval_idx, idx)
                noval_idx = None

    # logger.debug(":interpolate: last point %d: %f, %f" % (len(self.moves_st), self.moves_st[-1].speed(), self.moves_st[-1].altitude()))
    # i = 0
    # for f in self.moves:
    #     s = f.speed()
    #     a = f.altitude()
    #     logger.debug(":vnav: alter: %d: %f %f" % (i, s if s is not None else -1, a if a is not None else -1))
    #     i = i + 1

    return (True, ":interpolate: interpolated %s" % value)



def time(wpts):
    """
    Time 0 is start of array.
    """
    elapsed = 0
    currpos = wpts[0]
    currpos.setTime(elapsed)

    for idx in range(1, len(wpts)):
        nextpos = wpts[idx]
        d = distance(currpos, nextpos) * 1000 # km
        # logger.debug(":time: %s %s" % (nextpos.speed(), currpos.speed()))
        # if nextpos.speed() is None or nextpos.speed() is None:
        #     logger.debug(":time: positions: %d %s %s" % (idx, nextpos, currpos))
        s = (nextpos.speed() + currpos.speed()) / 2
        t = d / s  if s != 0 else 0 # km
        elapsed = elapsed + t
        nextpos.setTime(elapsed)
        currpos = nextpos

    # only show values of last iteration (can be moved inside loop)
    # logger.debug(":time: %3d: %10.3fm at %5.1fm/s = %6.1fs, total=%s" % (idx, d, currpos.speed(), t, timedelta(seconds=elapsed)))

    return (True, ":time: computed")



