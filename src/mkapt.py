import logging
from entity.airport import XPAirport, GeoJSONAirport

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("mkApt")

def main():

    a = GeoJSONAirport(icao="OTHH", iata="DOH", name="Hamad International Airport", city="Doha", country="Qatar", region="OT", lat=0, lon=0, alt=0)
    logger.debug("loading..")
    a.load()
    logger.debug("..done")

main()
