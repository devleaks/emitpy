"""
Export movement to be played by Living Scenery Technology
"""
import io
import logging
from emitpy.constants import EMIT_TYPE

logger = logging.getLogger("toLST")


DREF_DAYS = "sim/time/local_date_days"
DREF_TIME = "sim/time/local_time_sec"

OBJ_LIB_PATH = "emitpy/"


def toLST(emit):
    """
    Export movement to be played by Living Scenery Technology.
    We need the emit because Movement are not scheduled.
    """
    output = io.StringIO()
    contents = ""

    # Preparation
    move_id = ""
    mesh_id = ""
    if emit.emit_type == EMIT_TYPE.SERVICE.value:
        move_id = emit.move.service.getId()
        mesh_id = OBJ_LIB_PATH + emit.move.service.vehicle.icao.lower()
    elif emit.emit_type == EMIT_TYPE.MISSION.value:
        move_id = emit.move.mission.getId()
        mesh_id = OBJ_LIB_PATH + emit.move.mission.vehicle.icao.lower()
    else:
        logger.warning(f"invalid emit type {emit.emit_type}")
        return contents

    if len(emit.move_points) == 0:
        logger.warning("no movement point")
        return contents

    # Timing
    start_time = emit.curr_starttime
    if start_time is None:
        logger.warning("no emit start time")
        return contents
    day_of_year = int(start_time.timetuple().tm_yday)
    seconds_since_midnight = round((start_time - start_time.replace(hour=0, minute=0, second=0, microsecond=0)).total_seconds())

    # First, we block until we are the good day of the year, and start when we should
    # There is an issue when day > simulation day, or time > simulation time
    print(f"# emitpy generated for mission {move_id}", file=output)
    # block until good day to start movement
    print(f"DREFOP,NULL,NULL,NULL,NULL,{DREF_DAYS},{day_of_year}", file=output)
    # block until good time to start movement
    # !!! Expect issues around midnight !!!
    print(f"DREFOP,NULL,NULL,NULL,NULL,{DREF_TIME},{seconds_since_midnight}", file=output)

    print("# LOOP,<virtual lib path to object>", file=output)
    print(f"LOOP,{mesh_id}", file=output)

    # waypoints
    print("# WP,<lat>,<lon>,<speed(km/h)>", file=output)
    for p in emit.move_points:  # we don't need a WP at each emit point, only movement points are ok
        speed = round(p.speed() * 3.6, 1)  # m/s to km/h
        comment = p.comment()
        if comment is not None:
            print(f"# {comment}", file=output)
        print(f"WP,{p.lat()},{p.lon()},{speed}", file=output)
        pause = p.pause()
        if pause is not None:
            print(f"WAIT,{round(pause, 0)}", file=output)

    contents = output.getvalue()
    output.close()
    return contents
