import logging
from datetime import datetime

from emitpy.airspace import XPAirspace, Metar
from emitpy.business import Airline
from emitpy.aircraft import AircraftType, AircraftPerformance, Aircraft
from emitpy.flight import Arrival, Departure, ArrivalMove, DepartureMove
from emitpy.airport import Airport, AirportBase, XPAirport
from emitpy.emit import Emit
from emitpy.business import AirportManager
from emitpy.parameters import MANAGED_AIRPORT
from emitpy.utils import NAUTICAL_MILE

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
    metar = Metar.new(icao=MANAGED_AIRPORT["ICAO"])
    managed.setMETAR(metar=metar)  # calls prepareRunways()

    # Add pure commercial stuff
    qr = Airline.findIATA(iata="QR")
    airportManager.hub(managed, qr)

    # Create a pair of flights
    airline = qr
    # origin_apt = Airport.find("VOCL")

    MAXRANGE = 2000  # km

    arrrange = MAXRANGE + 1
    while(arrrange > MAXRANGE):
        (airline, origin_apt) = airportManager.selectRandomAirroute(airline=airline)
        arrrange = managed.miles(origin_apt)

    logger.debug("..loading origin airport..")
    origin_apt = AirportBase(icao=origin_apt.icao,
                             iata=origin_apt.iata,
                             name=origin_apt["properties"]["name"],
                             city=origin_apt["properties"]["city"],
                             country=origin_apt["properties"]["country"],
                             region=origin_apt.region,
                             lat=origin_apt["geometry"]["coordinates"][1],
                             lon=origin_apt["geometry"]["coordinates"][0],
                             alt=origin_apt["geometry"]["coordinates"][2] if len(origin_apt["geometry"]["coordinates"]) > 2 else None)
    ret = origin_apt.load()
    if not ret[0]:
        print("origin airport not loaded")

    origin_metar = Metar.new(icao=origin_apt.icao)
    origin_apt.setMETAR(metar=origin_metar)  # calls prepareRunways()

    destination_apt = None
    deprange = MAXRANGE + 1
    while(deprange > MAXRANGE):
        (airline, destination_apt) = airportManager.selectRandomAirroute(airline=airline)
        deprange = managed.miles(destination_apt)

    logger.debug("..loading destination airport..")
    destination_apt = AirportBase(icao=destination_apt.icao,
                                  iata=destination_apt.iata,
                                  name=destination_apt["properties"]["name"],
                                  city=destination_apt["properties"]["city"],
                                  country=destination_apt["properties"]["country"],
                                  region=destination_apt.region,
                                  lat=destination_apt["geometry"]["coordinates"][1],
                                  lon=destination_apt["geometry"]["coordinates"][0],
                                  alt=destination_apt["geometry"]["coordinates"][2] if len(destination_apt["geometry"]["coordinates"]) > 2 else None)
    ret = destination_apt.load()
    if not ret[0]:
        print("destination airport not loaded")

    destination_metar = Metar.new(icao=destination_apt.icao)
    destination_apt.setMETAR(metar=destination_metar)  # calls prepareRunways()
    logger.debug("..done")

    logger.debug("loading aircraft..")
    acperf = AircraftPerformance.findAircraftForRange(reqrange=arrrange)
    reqfl = acperf.FLFor(max(arrrange, deprange))
    aircraft = Aircraft(registration="A7-PMA", icao24= "a2ec4f", actype=acperf, operator=airline)
    logger.debug("..done")


    logger.debug("*" * 90)
    logger.info("*** (%s, %dnm) %s-%s %s-%s (%s, %dnm) AC %s at FL%d" % (
                origin_apt["properties"]["city"], arrrange/NAUTICAL_MILE, origin_apt.iata, MANAGED_AIRPORT["IATA"],
                MANAGED_AIRPORT["IATA"], destination_apt.iata, destination_apt["properties"]["city"], deprange/NAUTICAL_MILE,
                acperf.typeId, reqfl))
    logger.debug("*" * 90)

    logger.debug("creating arrival..")
    arr = Arrival(operator=airline, number="196", scheduled="2022-01-18T14:00:00+02:00", managedAirport=managed, origin=origin_apt, aircraft=aircraft)
    arr.setFL(reqfl)
    ramp = managed.selectRamp(arr)  # Aircraft won't get towed
    arr.setRamp(ramp)
    gate = "C99"
    ramp_name = ramp.getName()
    if ramp_name[0] in "A,B,C,D,E".split(",") and len(ramp) < 5:  # does now work for "Cargo Ramp F5" ;-)
        gate = ramp_name
    arr.setGate(gate)
    logger.debug("..planning..")
    arr.plan()
    logger.debug("..flying..")
    am = ArrivalMove(arr, managed)
    am.move()
    am.save()
    logger.debug("..broadcasting..")
    ae = Emit(am)
    ae.emit(30)
    ae.save()
    logger.debug("..arrived.")

    logger.debug("creating departure..")
    dep = Departure(operator=airline, number="195", scheduled="2022-01-18T16:00:00+02:00", managedAirport=managed, destination=destination_apt, aircraft=aircraft)
    dep.setFL(reqfl)
    dep.setRamp(ramp)
    dep.setGate(gate)
    logger.debug("..planning..")
    dep.plan()
    logger.debug("..flying..")
    dm = DepartureMove(dep, managed)
    dm.move()
    dm.save()
    # logger.debug("..broadcasting..")
    # de = Emit(dm)
    # de.emit(30)
    # de.save()
    logger.debug("..gone.")

    print(arr)
    print(dep)

main()