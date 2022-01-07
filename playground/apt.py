import logging
from xpairport import XPAirport

logging.basicConfig(level=logging.DEBUG)  # filename=('FTG_log.txt')

def main():

    def hascode(f):
        if "properties" in f:
            if "type" in f["properties"]:
                return f["properties"]["type"] in ("1")
        return False

    a = XPAirport("OTHH")
    a.load()
    a.ldCIFP()

main()
