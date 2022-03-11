import logging
from datetime import datetime, timedelta

from entity.airspace import XPAirspace, Metar
from entity.business import Airline
from entity.aircraft import AircraftType, AircraftPerformance, Aircraft
from entity.flight import Arrival, Departure, ArrivalMove, DepartureMove
from entity.airport import Airport, AirportBase, XPAirport
from entity.emit import Emit, BroadcastToFile, ADSB
from entity.business import AirportManager
from entity.parameters import MANAGED_AIRPORT
from entity.constants import FLIGHT_PHASE
from entity.utils import NAUTICAL_MILE

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

    logger.debug("..collecting METAR..")
    # Prepare airport for each movement
    metar = Metar(icao=MANAGED_AIRPORT["ICAO"])
    managed.setMETAR(metar=metar)  # calls prepareRunways()

    logger.debug("..done")

    # Add pure commercial stuff
    qr = Airline.findIATA(iata="QR")
    airportManager.hub(managed, qr)
    airline = qr

    (airline, remote_apt) = airportManager.selectRandomAirroute(airline=airline)
    aptrange = managed.miles(remote_apt)

    logger.debug("loading other airport..")
    remote_apt = AirportBase(icao=remote_apt.icao,
                             iata=remote_apt.iata,
                             name=remote_apt["properties"]["name"],
                             city=remote_apt["properties"]["city"],
                             country=remote_apt["properties"]["country"],
                             region=remote_apt.region,
                             lat=remote_apt["geometry"]["coordinates"][1],
                             lon=remote_apt["geometry"]["coordinates"][0],
                             alt=remote_apt["geometry"]["coordinates"][2] if len(remote_apt["geometry"]["coordinates"]) > 2 else None)
    ret = remote_apt.load()
    if not ret[0]:
        print("origin airport not loaded")

    logger.debug("..collecting METAR..")
    origin_metar = Metar(icao=remote_apt.icao)
    remote_apt.setMETAR(metar=origin_metar)  # calls prepareRunways()
    logger.debug("..done")


    logger.debug("loading aircraft..")
    acperf = AircraftPerformance.findAircraft(reqrange=aptrange)
    reqfl = acperf.FLFor(aptrange)
    aircraft = Aircraft(registration="A7-PMA", icao24= "a2ec4f", actype=acperf, operator=airline)
    logger.debug("..done")


    logger.debug("*" * 90)
    logger.info("*** (%s, %dnm) %s-%s AC %s at FL%d" % (
                remote_apt["properties"]["city"], aptrange/NAUTICAL_MILE, remote_apt.iata, MANAGED_AIRPORT["IATA"],
#                 MANAGED_AIRPORT["IATA"], destination_apt.iata, destination_apt["properties"]["city"], deprange/NAUTICAL_MILE,
                acperf.typeId, reqfl))
    logger.debug("*" * 90)

    logger.debug("creating flight..")
    arr = Arrival(operator=airline, number="196", scheduled="2022-01-18T14:00:00+02:00", managedAirport=managed, origin=remote_apt, aircraft=aircraft)
    # dep = Departure(operator=airline, number="195", scheduled="2022-01-18T16:00:00+02:00", managedAirport=managed, destination=destination_apt, aircraft=aircraft)
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
    logger.debug("..flying..")
    am = ArrivalMove(arr, managed)
    am.move()
    am.save()
    logger.debug("..emission positions..")
    ae = Emit(am)
    ae.emit(30)
    ae.save()

    print(ae.getMarkList())
    ae.schedule(FLIGHT_PHASE.TOUCH_DOWN.value, datetime.now() + timedelta(minutes=5))

    logger.debug("..broadcasting positions..")

    b = BroadcastToFile(ae, datetime.now(), ADSB)
    b.run()

    logger.debug("..done.")


main()
