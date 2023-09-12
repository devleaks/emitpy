import io
import logging
from datetime import datetime
from emitpy.constants import EMIT_TYPE

logger = logging.getLogger("toLST")



# sim/time/local_date_days
# sim/time/local_time_sec
DREF_DAYS = "sim/time/local_date_days"
DREF_TIME = "sim/time/local_time_sec"

def toLST(emit):
    output = io.StringIO()
    contents = ""

    # Preparation
    move_id = ""
    mesh_path = ""
    if emit.emit_type == EMIT_TYPE.SERVICE.value:
        move_id = emit.move.service.getId()
        mesh_id = emit.move.service.vehicle.icao.lower()
        scheduled = emit.move.service.scheduled
    elif emit.emit_type == EMIT_TYPE.MISSION.value:
        move_id = emit.move.mission.getId()
        mesh_id = emit.move.mission.vehicle.icao.lower()
        scheduled = emit.move.mission.scheduled
    else:
        logger.warning(f"invalid emit type {emit.emit_type}")
        return ""

    # Timing
    if len(emit._emit_points[0]) == 0:
        logger.warning("no emit point")
        return contents

    start_point = emit._emit_points[0]
    start_ts = start_point.getAbsoluteEmissionTime()
    if start_ts is None:
        logger.warning("no start time on first emit point")
        return contents

    start_time = datetime.fromtimestamp(start_ts)
    # set local timezone to match sim time
    if scheduled is not None:
        start_time.astimezone(tz=scheduled.tzinfo)
    else:
        logger.warning(f"no time zone information for {move_id}")

    day_of_year = int(start_time.timetuple().tm_yday)
    seconds_since_midnight = round((start_time - start_time.replace(hour=0, minute=0, second=0, microsecond=0)).total_seconds())

    # First, we block until we are the good day of the year, and start when we should
    # There is an issue when day > simulation day, or time > simulation time
    print(f"# emitpy generated for mission {move_id}", file=output)
    print(f"DREFOP,NULL,NULL,NULL,NULL,{DREF_DAYS},{day_of_year}", file=output)
    print(f"DREFOP,NULL,NULL,NULL,NULL,{DREF_TIME},{seconds_since_midnight}", file=output)

    print(f"# LOOP,<virtual lib path to object>", file=output)
    print(f"LOOP,{mesh_id}", file=output)

    # object
    # for now, object vitrual path is icao code.
    # later, should use mesh attribute. If len(mesh) > 1, should use TRAIN rather than LOOP
    if emit.emit_type == EMIT_TYPE.SERVICE.value:
        print(f"# emitpy generated for service {emit.move.service.getId()}", file=output)
        print(f"# LOOP,<virtual lib path to object>", file=output)
        print(f"LOOP,{emit.move.service.vehicle.icao.lower()}", file=output)
    elif emit.emit_type == EMIT_TYPE.MISSION.value:
        print(f"# emitpy generated for mission {emit.move.mission.getId()}", file=output)
        print(f"# LOOP,<virtual lib path to object>", file=output)
        print(f"LOOP,{emit.move.mission.vehicle.icao.lower()}", file=output)
    else:
        logger.warning(f"invalid emit type {emit.emit_type}")
        return ""

    # waypoints
    print(f"# WP,<lat>,<lon>,<speed(km/h)>", file=output)
    for p in emit._emit_points:
        speed = round(p.speed() * 3.6,1)  # m/s to km/h
        print(f"WP,{p.lat()},{p.lon()},{speed}", file=output)
        pause = p.pause()
        if pause is not None:
            print(f"WAIT,{round(pause, 2)}", file=output)

    contents = output.getvalue()
    output.close()
    return contents
