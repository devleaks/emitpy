from .key import key_path, rejson, rejson_keys
from .time import roundTime, actual_time
from .interpolate import compute_headings, compute_time, interpolate
from .timezone import Timezone
from .case import KebabToCamel
from .unitconversion import convert, sign

import os
from emitpy import __NAME__ as name
from emitpy.parameters import HOME_DIR

PROG_BASE = f"<{name}>"


def show_path(p: str) -> str:
    return os.path.abspath(p).replace(os.path.abspath(HOME_DIR), PROG_BASE)
