import sys
import logging

sys.path.append("..")

from emitpy.utils import convert, toKmh

FORMAT = "%(levelname)1.1s%(module)22s:%(funcName)-25s%(lineno)4s| %(message)s"
logging.basicConfig(level=logging.DEBUG, format=FORMAT)
logger = logging.getLogger("emit_flights")


class Situation:
    def __init__(self, speed: int, vert_speed: int, alt: int) -> None:
        self.speed = speed  # kn
        self.vert_speed = vert_speed  # ft/min
        self.alt = alt


def go(start, end, dist):
    # SPEED
    acc = end.speed - start.speed
    vacc = end.vert_speed - start.vert_speed
    clb = end.alt - start.alt

    # linear accel/decel
    avg_speed = (start.speed + end.speed) / 2
    t = dist / (avg_speed / 3600)
    print("distance", dist)
    print("avg speed", avg_speed)
    print("avg time", t)

    # accel/decel
    print("speed change", acc)
    accel = acc / t
    print("acc", accel)
    if -1 < accel < 1.5:
        print("accel/decel possible")
    else:
        print("impossible accel/decel")

    # ALT
    print("d.alt", clb)
    avg_vert_speed = (start.vert_speed + end.vert_speed) / 2
    if -4000 < avg_vert_speed < 4000:
        print("v/s possible")
    else:
        print("impossible to reach v/s")
    print("avg v/s", avg_vert_speed)
    print("v/s acc", (vacc / 60) / t)
    dalt = avg_vert_speed * t / 60
    print("potential d.alt", dalt)  # ft/min
    if dalt >= clb:
        print("delta altitude possible")
    else:
        print("impossible to reach altitude")


start0 = Situation(speed=140, vert_speed=0, alt=0)  # v/s 2000 ft/min gives 10 FLs in 5 minutes
end0 = Situation(speed=190, vert_speed=1000, alt=400)
dist0 = 2  # nm


go(start0, end0, dist0)
