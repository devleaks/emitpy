"""
Test API for flightplandatabase with request caching.

"""
from emitpy.airspace.metar import Metar


def main():

    m = Metar("OTHH")
    print(m.raw["METAR"])


if __name__ == "__main__":
    main()
