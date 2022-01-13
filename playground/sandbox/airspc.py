import logging
from xpairspace import XPAirspace

logging.basicConfig(level=logging.DEBUG)

def main():

    a = XPAirspace()
    a.load()

    a.mkRoute("OMDB", "OTBD")

main()
