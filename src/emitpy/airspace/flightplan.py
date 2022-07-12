"""
Flight plans are generated  by the flightplandatabase.com site and cached in this application.
Origin and destination airport details data is also cached.
(We suspect flightplan database uses the same X-Plane Arinc cycle 1802 dataset.)
"""
import logging
import copy

from geojson import Feature, FeatureCollection

from emitpy.airspace import Airspace, FlightPlanBase


logger = logging.getLogger("FlightPlan")


class FlightPlan(FlightPlanBase):

    def __init__(self, managedAirport, fromICAO: str, toICAO: str,
                 useNAT: bool = True, usePACOT: bool = True, useAWYLO: bool = True, useAWYHI: bool = True,
                 cruiseAlt: float = 35000, cruiseSpeed: float = 420,
                 ascentRate: float = 2500, ascentSpeed: float = 250,
                 descentRate: float = 1500, descentSpeed: float = 250,
                 force: bool = False):

        FlightPlanBase.__init__(self, managedAirport=managedAirport, fromICAO=fromICAO, toICAO=toICAO,
                                useNAT=useNAT, usePACOT=usePACOT, useAWYLO=useAWYLO, useAWYHI=useAWYHI,
                                cruiseAlt=cruiseAlt, cruiseSpeed=cruiseSpeed,
                                ascentRate=ascentRate, ascentSpeed=ascentSpeed,
                                descentRate=descentRate, descentSpeed=descentSpeed,
                                force=force)


    def getGeoJSON(self, include_ls: bool = False):
        # fluke-ignore F841
        dummy = self.getFlightPlan()
        if self.route is not None:
            fc = FeatureCollection(features=self.route.features)  # .copy()
            if include_ls:
                fc.features.append(Feature(geometry=self.routeLS, properties={"tag": "route"}))
            return fc

        return None


    def toAirspace(self, airspace: Airspace):
        """
        Transform [<Feature<Point>>] from FlightPlanDatabase into [<<Vertex>>] where Vertex is in Airspace.
        (Also possible to start from fpdb "nodes", since our <Feature<Point>> is actually built from it.)
        """
        def isPoint(f):
            return ("geometry" in f) and ("type" in f["geometry"]) and (f["geometry"]["type"] == "Point")

        wpts = []
        errs = 0
        last = None

        # From nodes in route:
        # for n in self.flight_plan["route"]["nodes"]:
        #     if isNodePoint(n):
        #         fty = n["type"] if "type" in n else None
        #         fid = n["ident"] if "ident" in n else None

        # From Features in collection:
        for f in self.route.features:
            if isPoint(f):
                fty = f["properties"]["type"] if "type" in f["properties"] else None
                fid = f["properties"]["ident"] if "ident" in f["properties"] else None
                if fid is not None:
                    wid = airspace.findControlledPointByIdent(fid)
                    if len(wid) == 1:
                        if wid[0] != last:
                            v = airspace.getControlledPoint(wid[0])
                            wpts.append(v)
                            last = wid[0]
                        else:
                            logger.debug(f":toAirspace: {last} same as previous")
                        # logger.debug(":toAirspace: added %s %s as %s" % (fty, fid, v.id))
                    elif len(wid) == 0:
                        errs = errs + 1
                        logger.warning(f":toAirspace: ident {fid} not found")
                    else:  # len(wid) > 1
                        logger.debug(f":toAirspace: ambiguous ident {fid} has {len(wid)} entries")
                        # @todo use proximity to previous point, choose closest. Use navaid rather than fix.
                        if len(wpts) > 0:
                            logger.debug(f":toAirspace: will search for closest to previous {wpts[-1].id}")
                            wid2 = airspace.findClosestControlledPoint(reference=wpts[-1].id, vertlist=wid)  # returns (wpt, dist)
                            if wid2[0] != last:
                                v = airspace.getControlledPoint(wid2[0])
                                wpts.append(v)
                                last = wid2[0]
                            else:
                                logger.debug(f":toAirspace: {last} same as previous")
                            logger.debug(f":toAirspace: added {fty} {fid} as {v.id} (closest waypoint at {wid2[1]:f})")
                        else:
                            errs = errs + 1
                            logger.debug(f":toAirspace: cannot determine ambiguous ident {fid} has {len(wid)} entries")
                else:
                    errs = errs + 1
                    logger.warning(f":toAirspace: no ident for feature {fid}")
        return (copy.deepcopy(wpts), errs)
