"""
Test API for flightplandatabase with request caching.

"""
from emitpy.airspace.metar import Metar
from emitpy.utils import Timezone
from datetime import datetime

dohatime = Timezone(offset=3, name="Doha")


def main():

    dt = datetime.strptime("2019-04-01 02:25:00", "%Y-%m-%d %H:%M:%S").replace(tzinfo=dohatime)
    m = Metar(icao="OTHH", use_redis=True)
    print(m.metar)


if __name__ == "__main__":
    main()
