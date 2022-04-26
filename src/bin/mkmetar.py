"""
Test API for flightplandatabase with request caching.

"""
import sys
sys.path.append('/Users/pierre/Developer/oscars/emitpy/src')
import logging


from emitpy.airspace.metar import Metar
from emitpy.utils import Timezone
from datetime import datetime

logging.basicConfig(level=logging.DEBUG)


dohatime = Timezone(offset=3, name="Doha")


def main():

    dt = datetime.strptime("2019-04-01 02:25:00", "%Y-%m-%d %H:%M:%S").replace(tzinfo=dohatime)
    m = Metar.new(icao="OTHH", method="MetarHistorical")
    m.setDatetime(moment=dt)
    print(m.metar, m.getInfo())


if __name__ == "__main__":
    main()