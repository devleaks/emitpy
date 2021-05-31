__VERSION__ = '0.1'
__NAME__ = "emitpy"
__DESCRIPTION__ = "Flight path generator."


from .aircraft import Aircraft
from .flightboard import Flightboard
from .location import Location
from .constant import Constant
from .metar import Metar

from .parameters import DATA_DIR
