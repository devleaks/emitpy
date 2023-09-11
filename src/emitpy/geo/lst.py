import io
import logging
from emitpy.constants import EMIT_TYPE

logger = logging.getLogger("toLST")


def toLST(emit):
    output = io.StringIO()

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
            print(f"PAUSE,{round(pause, 2)}", file=output)

    contents = output.getvalue()
    output.close()
    return contents
