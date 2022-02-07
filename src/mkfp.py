"""
Test API for flightplandatabase with request caching.

"""
import argparse
from entity.parameters import MANAGED_AIRPORT
from entity.airspace import FlightPlanBase


def main():
    parser = argparse.ArgumentParser(description="Get flight plan.")
    parser.add_argument("--fromICAO", "-f", nargs="?", type=str, help="departure")
    parser.add_argument("--toICAO", "-t", nargs="?", type=str, help="arrival")

    args = parser.parse_args()

    plan = FlightPlanBase(
        managedAirport=MANAGED_AIRPORT["ICAO"],
        fromICAO=args.fromICAO.upper(),
        toICAO=args.toICAO.upper(),
        cruiseAlt=30000,
        cruiseSpeed=380,
        ascentRate=2500,
        ascentSpeed=250,
        descentRate=1500,
        descentSpeed=250)

    print("got plan" if plan.getFlightPlan() is not None else "not found")

if __name__ == "__main__":
    main()
