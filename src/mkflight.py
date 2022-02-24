import logging
from datetime import datetime

from entity.business import Airline
from entity.airspace import XPAirspace, Metar
from entity.airport import Airport, AirportBase, XPAirport
from entity.aircraft import AircraftType, AircraftPerformance, Aircraft
from entity.flight import Arrival, Departure, Movement
from entity.emit import Emit
from entity.business import AirportManager
from entity.parameters import MANAGED_AIRPORT

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("mkFlight")


def main():

    airspace = XPAirspace()
    logger.debug("loading airspace..")
    airspace.load()
    logger.debug("..done")

    logger.debug("loading airport..")
    Airport.loadAll()
    logger.debug("..done")

    logger.debug("loading airlines..")
    Airline.loadAll()
    logger.debug("..done")

    logger.debug("loading aircrafts..")
    AircraftType.loadAll()
    AircraftPerformance.loadAll()
    logger.debug("..done")

    logger.debug("..done")

    logger.debug("loading managed airport..")

    logger.debug("..loading airport manager..")
    airportManager = AirportManager(icao=MANAGED_AIRPORT["ICAO"])
    airportManager.load()

    logger.debug("..loading managed airport..")
    managed = XPAirport(
        icao=MANAGED_AIRPORT["ICAO"],
        iata=MANAGED_AIRPORT["IATA"],
        name=MANAGED_AIRPORT["name"],
        city=MANAGED_AIRPORT["city"],
        country=MANAGED_AIRPORT["country"],
        region=MANAGED_AIRPORT["regionName"],
        lat=MANAGED_AIRPORT["lat"],
        lon=MANAGED_AIRPORT["lon"],
        alt=MANAGED_AIRPORT["elevation"])
    ret = managed.load()
    if not ret[0]:
        print("Managed airport not loaded")
    managed.setAirspace(airspace)

    # Prepare airport for each movement
    metar = Metar(icao=MANAGED_AIRPORT["ICAO"])
    managed.setMETAR(metar=metar)  # calls prepareRunways()

    # Add pure commercial stuff
    qr = Airline.findIATA(iata="QR")
    airportManager.hub(managed, qr)

    # Create a pair of flights
    airline = qr
    # other_airport = Airport.find("VOCL")

    reqrange = 45000
    while(reqrange > 3000):
        (airline, other_airport) = airportManager.getRandomAirroute(airline=airline)
        reqrange = managed.miles(other_airport)

    # upgrade
    logger.debug("..loading other airport..")
    other_airport = AirportBase(icao=other_airport.icao,
                                iata=other_airport.iata,
                                name=other_airport["properties"]["name"],
                                city=other_airport["properties"]["city"],
                                country=other_airport["properties"]["country"],
                                region=other_airport.region,
                                lat=other_airport["geometry"]["coordinates"][1],
                                lon=other_airport["geometry"]["coordinates"][0],
                                alt=other_airport["geometry"]["coordinates"][2] if len(other_airport["geometry"]["coordinates"]) > 2 else None)
    ret = other_airport.load()
    if not ret[0]:
        print("Other airport not loaded")

    other_metar = Metar(icao=other_airport.icao)
    other_airport.setMETAR(metar=other_metar)  # calls prepareRunways()

    logger.debug("..done")


    logger.debug("loading aircraft..")
    acperf = AircraftPerformance.findAircraft(reqrange=reqrange)
    reqfl = acperf.FLFor(reqrange)

    logger.info("FLIGHT ********** From/to %s (%dkm)(%s, %s) with %s (%s, %s)" % (other_airport["properties"]["city"], reqrange, other_airport.iata, other_airport.icao, airline.orgId, airline.iata, airline.icao))
    logger.info("       ********** Range is %dkm, aircraft will be %s at FL%d" % (reqrange, acperf.typeId, reqfl))

    aircraft = Aircraft(registration="A7-PMA", icao24= "a2ec4f", actype=acperf, operator=airline)
    logger.debug("..done")

    logger.debug("creating arrival..")
    arr = Arrival(operator=airline, number="196", scheduled="2022-01-18T14:00:00+02:00", managedAirport=managed, origin=other_airport, aircraft=aircraft)
    arr.setFL(reqfl)
    ramp = managed.selectRamp(arr)  # Aircraft won't get towed
    arr.setRamp(ramp)
    gate = "C99"
    ramp_name = ramp.getProp("name")
    if ramp_name[0] in "A,B,C,D,E".split(",") and len(ramp) < 5:  # does now work for "Cargo Ramp F5" ;-)
        gate = ramp_name
    arr.setGate(gate)
    logger.debug("..planning..")
    arr.plan()
    logger.debug("..done")

    # logger.debug("creating departure..")
    # dep = Departure(operator=airline, number="195", scheduled="2022-01-18T16:00:00+02:00", managedAirport=managed, destination=other_airport, aircraft=aircraft)
    # dep.setFL(reqfl)
    # dep.setRamp(ramp)
    # dep.setGate(gate)
    # logger.debug("..planning..")
    # dep.plan()
    # logger.debug("..done")

    logger.debug("flying..")
    am = Movement.create(arr, managed)
    am.make()
    am.save()

    # ae = Emit(am)
    # ae.emit()
    # ae.save()
    # f = ae.get("TOUCH_DOWN", datetime.now())

    # metar may change between the two
    # managed.setMETAR(metar=metar)  # calls prepareRunways()
    # dm = Movement.create(dep, managed)
    # dm.make()
    # dm.save()

    # de = Emit(am)
    # de.emit()
    # de.save()

    # f = ae.get("TAKE_OFF", datetime.now())

    logger.debug("..done")

main()
