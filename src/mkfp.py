"""
Test API for flightplandatabase with request caching.

"""
import argparse
from entity.airspace import FlightPlan

def main():
    parser = argparse.ArgumentParser(description="Get flight plan.")
    parser.add_argument("--fromICAO", "-f", nargs="?", type=str, help="departure")
    parser.add_argument("--toICAO", "-t", nargs="?", type=str, help="arrival")

    args = parser.parse_args()

    plan = FlightPlan(
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

