__VERSION__ = '0.1'
__NAME__ = "emitpy"
__DESCRIPTION__ = "Flight path generator."


from .airport import Airport, DetailedAirport
from .home import ManagedAirport
from .aircraft import Aircraft
from .flightboard import Flightboard
from .location import Location
from .geojson import Point
from .constant import Constant
from .metar import Metar

from .parameters import DATA_DIR
